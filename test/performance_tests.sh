#!/bin/bash

# Performance Tests for quaybkp
# These tests focus on performance characteristics and scalability
# NOTE: THESE TESTS DON'T WORK (YET)

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test counters
PERF_TESTS=0
PERF_PASSED=0
PERF_FAILED=0

# Test configuration
TEST_DIR="$(dirname "$0")"
PROJECT_ROOT="$(dirname "$TEST_DIR")"
QUAY_CONFIG="$TEST_DIR/config/config.yaml"
TEST_NAMESPACE="perftest"
TEST_BUCKET="quaybkp-perf"

# Override environment variables for testing
export QUAY_CONFIG="$QUAY_CONFIG"
export S3_ACCESS_KEY_ID="miniouser"
export S3_SECRET_ACCESS_KEY="miniopassword" 
export S3_ENDPOINT_URL="http://lab.local:7000"

# Container runtime (docker or podman)
CONTAINER_RUNTIME="${CONTAINER_RUNTIME:-docker}"

# Container TLS setting (for podman with HTTP)
CONTAINER_TLS="${CONTAINER_TLS:-}"

# MinIO client aliases
BACKUP_ALIAS="backup"
QUAY_ALIAS="quay"

# Test images for performance testing
TEST_IMAGES=(
    "docker.io/library/postgres:12.1"
    "docker.io/library/redis:latest"
    "docker.io/library/alpine:3.14"
    "docker.io/library/busybox:1.34"
)

log_perf() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> "$TEST_DIR/performance_test_results.log"
}

print_perf_header() {
    echo -e "${BLUE}================================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}================================================${NC}"
}

print_perf_test() {
    echo -e "${YELLOW}[PERF] $1${NC}"
    log_perf "[PERF] $1"
}

print_perf_success() {
    echo -e "${GREEN}[PASS] $1${NC}"
    log_perf "[PASS] $1"
    ((PERF_PASSED++))
}

print_perf_failure() {
    echo -e "${RED}[FAIL] $1${NC}"
    log_perf "[FAIL] $1"
    ((PERF_FAILED++))
}

increment_perf_test() {
    ((PERF_TESTS++))
}

run_quaybkp() {
    python -m quaybkp.main "$@" 2>&1
}

setup_performance_environment() {
    print_perf_test "Setting up performance test environment"
    increment_perf_test
    
    # Configure MinIO aliases
    mc alias set "$BACKUP_ALIAS" "$S3_ENDPOINT_URL" "$S3_ACCESS_KEY_ID" "$S3_SECRET_ACCESS_KEY" >/dev/null 2>&1
    mc alias set "$QUAY_ALIAS" "http://lab.local:9000" "miniouser" "miniopassword" >/dev/null 2>&1
    
    # Verify buckets exist (should be created by Quay and backup tool)
    if ! mc ls "$QUAY_ALIAS/quaybucket" >/dev/null 2>&1; then
        print_perf_failure "Quay storage bucket does not exist"
        return 1
    fi
    
    print_perf_success "Performance environment setup completed"
}

create_large_test_dataset() {
    local image_count=$1
    print_perf_test "Creating test dataset by pushing $image_count container images using $CONTAINER_RUNTIME"
    increment_perf_test
    
    # Login to Quay
    if ! echo "password" | $CONTAINER_RUNTIME login "lab.local:8080" -u "quayadmin" --password-stdin >/dev/null 2>&1; then
        print_perf_failure "Failed to login to Quay"
        return 1
    fi
    
    # Push multiple copies of test images to create more blobs
    local images_pushed=0
    for ((i=1; i<=image_count; i++)); do
        local base_image="${TEST_IMAGES[$((i % ${#TEST_IMAGES[@]}))]}"
        local image_name=$(echo "$base_image" | cut -d'/' -f3 | cut -d':' -f1)
        local image_tag="perf-test-$i"
        local quay_image="lab.local:8080/$TEST_NAMESPACE/$image_name:$image_tag"
        
        if $CONTAINER_RUNTIME pull "$CONTAINER_TLS" "$base_image" >/dev/null 2>&1 && \
           $CONTAINER_RUNTIME tag "$base_image" "$quay_image" >/dev/null 2>&1 && \
           $CONTAINER_RUNTIME push "$CONTAINER_TLS" "$quay_image" >/dev/null 2>&1; then
            ((images_pushed++))
            if [ $((i % 5)) -eq 0 ]; then
                echo -n "."
            fi
        fi
    done
    echo ""
    
    # Wait for Quay to process
    sleep 5
    
    # Verify blobs were created
    local blob_count=$(mc ls --recursive "$QUAY_ALIAS/quaybucket/datastorage/registry/sha256/" 2>/dev/null | wc -l || echo "0")
    if [ "$blob_count" -ge "$images_pushed" ]; then
        print_perf_success "Created test dataset with $images_pushed images ($blob_count blobs)"
    else
        print_perf_failure "Failed to create sufficient test dataset"
        return 1
    fi
}

test_backup_performance() {
    print_perf_header "Testing Backup Performance"
    
    # Test with different image counts (which create different numbers of blobs)
    local image_counts=(5 10 15)
    local worker_counts=(1 3 5 10)
    
    for image_count in "${image_counts[@]}"; do
        create_large_test_dataset "$image_count"
        
        for worker_count in "${worker_counts[@]}"; do
            print_perf_test "Testing backup performance: $image_count images, $worker_count workers"
            increment_perf_test
            
            # Clean backup bucket
            mc rm --recursive --force "$BACKUP_ALIAS/$TEST_BUCKET" >/dev/null 2>&1 || true
            
            # Time the backup operation
            start_time=$(date +%s)
            if run_quaybkp backup "$TEST_NAMESPACE" --bucket-name "$TEST_BUCKET" --num-workers "$worker_count" >/dev/null 2>&1; then
                end_time=$(date +%s)
                duration=$((end_time - start_time))
                rate=$(echo "scale=2; $image_count / $duration" | bc -l 2>/dev/null || echo "N/A")
                
                print_perf_success "Backup completed in ${duration}s (${rate} images/sec) with $worker_count workers"
                log_perf "PERFORMANCE: $image_count images, $worker_count workers, ${duration}s, ${rate} images/sec"
            else
                print_perf_failure "Backup failed with $worker_count workers"
            fi
        done
    done
}

test_restore_performance() {
    print_perf_header "Testing Restore Performance"
    
    # Create a baseline backup
    create_large_test_dataset 10
    run_quaybkp backup "$TEST_NAMESPACE" --bucket-name "$TEST_BUCKET" >/dev/null 2>&1
    
    local worker_counts=(1 3 5 10)
    
    for worker_count in "${worker_counts[@]}"; do
        print_perf_test "Testing restore performance with $worker_count workers"
        increment_perf_test
        
        # Clear Quay storage (this will remove the actual blobs from storage)
        mc rm --recursive --force "$QUAY_ALIAS/quaybucket/datastorage/" >/dev/null 2>&1 || true
        
        # Time the restore operation
        start_time=$(date +%s)
        if run_quaybkp restore "$TEST_NAMESPACE" --bucket-name "$TEST_BUCKET" --num-workers "$worker_count" >/dev/null 2>&1; then
            end_time=$(date +%s)
            duration=$((end_time - start_time))
            rate=$(echo "scale=2; 10 / $duration" | bc -l 2>/dev/null || echo "N/A")
            
            print_perf_success "Restore completed in ${duration}s (${rate} images/sec) with $worker_count workers"
            log_perf "RESTORE PERFORMANCE: 10 images, $worker_count workers, ${duration}s, ${rate} images/sec"
        else
            print_perf_failure "Restore failed with $worker_count workers"
        fi
    done
}

test_verify_performance() {
    print_perf_header "Testing Verify Performance"
    
    # Use existing backup from restore tests
    local blob_counts=(50 100)
    
    for blob_count in "${blob_counts[@]}"; do
        print_perf_test "Testing verify performance with $blob_count blobs"
        increment_perf_test
        
        create_large_test_dataset "$blob_count"
        run_quaybkp backup "$TEST_NAMESPACE" --bucket-name "$TEST_BUCKET" >/dev/null 2>&1
        
        # Time the verify operation
        start_time=$(date +%s)
        if run_quaybkp verify "$TEST_NAMESPACE" --bucket-name "$TEST_BUCKET" >/dev/null 2>&1; then
            end_time=$(date +%s)
            duration=$((end_time - start_time))
            rate=$(echo "scale=2; $blob_count / $duration" | bc -l 2>/dev/null || echo "N/A")
            
            print_perf_success "Verify completed in ${duration}s (${rate} blobs/sec)"
            log_perf "VERIFY PERFORMANCE: $blob_count blobs, ${duration}s, ${rate} blobs/sec"
        else
            print_perf_failure "Verify failed"
        fi
    done
}

test_concurrent_operations() {
    print_perf_header "Testing Concurrent Operations"
    
    print_perf_test "Testing concurrent backup attempts (should be blocked by lock)"
    increment_perf_test
    
    create_large_test_dataset 30
    mc rm --recursive --force "$BACKUP_ALIAS/$TEST_BUCKET" >/dev/null 2>&1 || true
    
    # Start first backup in background
    run_quaybkp backup "$TEST_NAMESPACE" --bucket-name "$TEST_BUCKET" >/dev/null 2>&1 &
    backup_pid=$!
    
    # Wait a moment for lock to be created
    sleep 2
    
    # Try second backup (should fail due to lock)
    start_time=$(date +%s)
    if run_quaybkp backup "$TEST_NAMESPACE" --bucket-name "$TEST_BUCKET" 2>&1 | grep -q "in progress"; then
        end_time=$(date +%s)
        duration=$((end_time - start_time))
        print_perf_success "Concurrent backup correctly blocked in ${duration}s"
    else
        print_perf_failure "Concurrent backup was not blocked"
    fi
    
    # Wait for first backup to complete
    wait $backup_pid || true
}

test_memory_usage() {
    print_perf_header "Testing Memory Usage"
    
    print_perf_test "Testing memory usage during large backup"
    increment_perf_test
    
    create_large_test_dataset 100
    mc rm --recursive --force "$BACKUP_ALIAS/$TEST_BUCKET" >/dev/null 2>&1 || true
    
    # Monitor memory usage during backup
    if command -v ps &> /dev/null; then
        # Start backup in background
        run_quaybkp backup "$TEST_NAMESPACE" --bucket-name "$TEST_BUCKET" >/dev/null 2>&1 &
        backup_pid=$!
        
        # Monitor memory usage
        max_memory=0
        while kill -0 $backup_pid 2>/dev/null; do
            if command -v ps &> /dev/null; then
                memory=$(ps -o rss= -p $backup_pid 2>/dev/null || echo "0")
                if [ "$memory" -gt "$max_memory" ]; then
                    max_memory=$memory
                fi
            fi
            sleep 1
        done
        
        # Convert KB to MB
        max_memory_mb=$(echo "scale=2; $max_memory / 1024" | bc -l 2>/dev/null || echo "N/A")
        
        if [ "$max_memory" -gt 0 ]; then
            print_perf_success "Peak memory usage: ${max_memory_mb} MB"
            log_perf "MEMORY USAGE: Peak ${max_memory_mb} MB for 100 blobs"
        else
            print_perf_failure "Could not measure memory usage"
        fi
        
        wait $backup_pid || true
    else
        print_perf_failure "ps command not available for memory testing"
    fi
}

test_scalability_limits() {
    print_perf_header "Testing Scalability Limits"
    
    print_perf_test "Testing with maximum worker count"
    increment_perf_test
    
    create_large_test_dataset 50
    mc rm --recursive --force "$BACKUP_ALIAS/$TEST_BUCKET" >/dev/null 2>&1 || true
    
    # Test with very high worker count
    start_time=$(date +%s)
    if run_quaybkp backup "$TEST_NAMESPACE" --bucket-name "$TEST_BUCKET" --num-workers 20 >/dev/null 2>&1; then
        end_time=$(date +%s)
        duration=$((end_time - start_time))
        print_perf_success "High worker count (20) completed in ${duration}s"
        log_perf "SCALABILITY: 20 workers, 50 blobs, ${duration}s"
    else
        print_perf_failure "High worker count failed"
    fi
    
    print_perf_test "Testing with single worker (baseline)"
    increment_perf_test
    
    mc rm --recursive --force "$BACKUP_ALIAS/$TEST_BUCKET" >/dev/null 2>&1 || true
    
    start_time=$(date +%s)
    if run_quaybkp backup "$TEST_NAMESPACE" --bucket-name "$TEST_BUCKET" --num-workers 1 >/dev/null 2>&1; then
        end_time=$(date +%s)
        duration=$((end_time - start_time))
        print_perf_success "Single worker completed in ${duration}s"
        log_perf "BASELINE: 1 worker, 50 blobs, ${duration}s"
    else
        print_perf_failure "Single worker failed"
    fi
}

cleanup_performance_tests() {
    print_perf_test "Cleaning up performance test data"
    
    # Remove backup test data
    mc rm --recursive --force "$BACKUP_ALIAS/$TEST_BUCKET" >/dev/null 2>&1 || true
    
    # Remove test images from Quay via API
    for image in "${TEST_IMAGES[@]}"; do
        local image_name=$(echo "$image" | cut -d'/' -f3 | cut -d':' -f1)
        curl -s -X DELETE \
            -u "quayadmin:password" \
            "http://lab.local:8080/api/v1/repository/$TEST_NAMESPACE/$image_name" >/dev/null 2>&1 || true
    done
    
    # Clean up local container images
    for image in "${TEST_IMAGES[@]}"; do
        $CONTAINER_RUNTIME rmi "$image" >/dev/null 2>&1 || true
    done
    
    print_perf_success "Performance test cleanup completed"
}

# Main performance test execution
main_perf() {
    print_perf_header "Quay Blob Backup and Restore Tool - Performance Tests"
    
    # Check for required tools
    if ! command -v bc &> /dev/null; then
        echo -e "${RED}Error: bc calculator is required for performance tests${NC}"
        exit 1
    fi
    
    if ! command -v "$CONTAINER_RUNTIME" &> /dev/null; then
        echo -e "${RED}Error: $CONTAINER_RUNTIME is not installed or not in PATH${NC}"
        exit 1
    fi
    
    # Initialize log file
    echo "Performance test run started at $(date)" > "$TEST_DIR/performance_test_results.log"
    
    # Setup
    setup_performance_environment
    
    # Run all performance tests
    test_backup_performance
    test_restore_performance
    test_verify_performance
    test_concurrent_operations
    test_memory_usage
    test_scalability_limits
    
    # Cleanup
    cleanup_performance_tests
    
    # Print results
    print_perf_header "Performance Test Results Summary"
    echo -e "${BLUE}Total Performance Tests: $PERF_TESTS${NC}"
    echo -e "${GREEN}Passed: $PERF_PASSED${NC}"
    echo -e "${RED}Failed: $PERF_FAILED${NC}"
    
    # Print performance summary from log
    if [ -f "$TEST_DIR/performance_test_results.log" ]; then
        echo -e "${BLUE}Performance Summary:${NC}"
        grep "PERFORMANCE\|BASELINE\|MEMORY USAGE" "$TEST_DIR/performance_test_results.log" | tail -10
    fi
    
    if [ $PERF_FAILED -eq 0 ]; then
        echo -e "${GREEN}All performance tests passed!${NC}"
        return 0
    else
        echo -e "${RED}Some performance tests failed.${NC}"
        return 1
    fi
}

# Run main function
#main_perf "$@"
echo -e "${RED}Performance tests are not fully working yet..."
return 1