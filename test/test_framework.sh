#!/bin/bash

# Comprehensive Test Framework for quaybkp
# This script tests all functionality of the Quay Blob Backup and Restore Tool

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test counters
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

# Test configuration
TEST_DIR="$(dirname "$0")"
PROJECT_ROOT="$(dirname "$TEST_DIR")"
QUAY_CONFIG="$TEST_DIR/config/config.yaml"
TEST_NAMESPACE="testnamespace"
TEST_BUCKET="quaybkp-test"

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

# Test images to push to Quay
TEST_IMAGES=(
    "docker.io/library/postgres:12.1"
    "docker.io/library/redis:latest"
    "docker.io/library/alpine:3.14"
    "docker.io/library/busybox:1.34"
)

# Quay server configuration
QUAY_SERVER="lab.local:8080"
QUAY_USERNAME="quayadmin"
QUAY_PASSWORD="password"

# Logging
LOG_FILE="$TEST_DIR/test_results.log"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOG_FILE"
}

print_header() {
    echo -e "${BLUE}================================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}================================================${NC}"
}

print_test() {
    echo -e "${YELLOW}[TEST] $1${NC}"
    log "[TEST] $1"
}

print_success() {
    echo -e "${GREEN}[PASS] $1${NC}"
    log "[PASS] $1"
    PASSED_TESTS=$((PASSED_TESTS + 1))
}

print_failure() {
    echo -e "${RED}[FAIL] $1${NC}"
    log "[FAIL] $1"
    FAILED_TESTS=$((FAILED_TESTS + 1))
}

increment_test() {
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
}

# Test helper functions
#run_quaybkp() {
#    python -m quaybkp.main "$@" 2>&1
#}

check_command_exists() {
    if ! command -v "$1" &> /dev/null; then
        echo -e "${RED}Error: $1 is not installed or not in PATH${NC}"
        exit 1
    fi
}

setup_minio_aliases() {
    print_test "Setting up MinIO client aliases"
    increment_test
    
    # Configure backup storage alias
    if mc alias set "$BACKUP_ALIAS" "$S3_ENDPOINT_URL" "$S3_ACCESS_KEY_ID" "$S3_SECRET_ACCESS_KEY" >/dev/null 2>&1; then
        print_success "Configured backup storage alias"
    else
        print_failure "Failed to configure backup storage alias"
        return 1
    fi
    
    # Configure Quay storage alias  
    if mc alias set "$QUAY_ALIAS" "http://lab.local:9000" "miniouser" "miniopassword" >/dev/null 2>&1; then
        print_success "Configured Quay storage alias"
    else
        print_failure "Failed to configure Quay storage alias"
        return 1
    fi
}

verify_buckets_exist() {
    print_test "Verifying storage buckets exist"
    increment_test
    
    # Verify backup bucket exists (should be created by backup tool)
    if mc ls "$BACKUP_ALIAS/$TEST_BUCKET" >/dev/null 2>&1; then
        print_success "Backup bucket exists: $TEST_BUCKET"
    else
        log "Backup bucket will be created by backup tool when needed"
        print_success "Backup bucket will be auto-created"
    fi
    
    # Verify Quay storage bucket exists (should be created by Quay)
    if mc ls "$QUAY_ALIAS/quaybucket" >/dev/null 2>&1; then
        print_success "Quay storage bucket exists: quaybucket"
    else
        print_failure "Quay storage bucket does not exist: quaybucket"
        return 1
    fi
}

login_to_quay() {
    print_test "Logging into Quay registry using $CONTAINER_RUNTIME"
    increment_test
    
    if echo "$QUAY_PASSWORD" | $CONTAINER_RUNTIME login "$QUAY_SERVER" "$CONTAINER_TLS" -u "$QUAY_USERNAME" --password-stdin >/dev/null 2>&1; then
        print_success "Successfully logged into Quay"
    else
        print_failure "Failed to login to Quay"
        return 1
    fi
}

create_test_namespace() {
    print_test "Creating test namespace in Quay"
    increment_test
      
    # Try to create namespace via Quay API- this might fail if it's already there, that's okay
    local response=$(curl -s -X POST \
        -H "Authorization: Bearer $QUAYADMINTOKEN" \
        -H "Content-Type: application/json" \
        -d "{\"name\": \"$TEST_NAMESPACE\"}" \
        "http://$QUAY_SERVER/api/v1/organization/" 2>/dev/null)
    
    # Check if namespace exists or was created
    local check_response=$(curl -s \
        -H "Authorization: Bearer $QUAYADMINTOKEN" \
        "http://$QUAY_SERVER/api/v1/organization/$TEST_NAMESPACE" 2>/dev/null)
    
    if echo "$check_response" | grep -q "\"name\".*\"$TEST_NAMESPACE\"" || echo "$response" | grep -q "success\|created"; then
        print_success "Test namespace ready: $TEST_NAMESPACE"
    else
        print_failure "Failed to create/verify test namespace"
        return 1
    fi
}

push_test_images() {
    print_test "Pushing test images to Quay using $CONTAINER_RUNTIME"
    increment_test
    
    local images_pushed=0
    local total_images=${#TEST_IMAGES[@]}
    
    for image in "${TEST_IMAGES[@]}"; do
        local image_name=$(echo "$image" | cut -d'/' -f3 | cut -d':' -f1)
        local image_tag=$(echo "$image" | cut -d':' -f2)
        local quay_image="$QUAY_SERVER/$TEST_NAMESPACE/$image_name:$image_tag"
        
        echo "  Pulling $image..."
        if $CONTAINER_RUNTIME pull "$CONTAINER_TLS" "$image" >/dev/null 2>&1; then
            echo "  Tagging as $quay_image..."
            if $CONTAINER_RUNTIME tag "$image" "$quay_image" >/dev/null 2>&1; then
                echo "  Pushing to Quay..."
                if $CONTAINER_RUNTIME push "$CONTAINER_TLS" "$quay_image" >/dev/null 2>&1; then
                    images_pushed=$((images_pushed + 1))
                    echo "  ✓ Successfully pushed $image_name:$image_tag"
                else
                    echo "  ✗ Failed to push $image_name:$image_tag"
                fi
            else
                echo "  ✗ Failed to tag $image_name:$image_tag"
            fi
        else
            echo "  ✗ Failed to pull $image"
        fi
    done
    
    if [ "$images_pushed" -ge 2 ]; then
        print_success "Pushed $images_pushed/$total_images test images successfully"
    else
        print_failure "Failed to push enough test images ($images_pushed/$total_images)"
        return 1
    fi
}

setup_test_data() {
    print_test "Setting up test data using real container images"
    
    login_to_quay
    create_test_namespace  
    push_test_images
    
    # Wait for Quay to process the images and create blobs
    print_test "Waiting for Quay to process pushed images"
    increment_test
    sleep 10
    
    # Verify blobs exist in Quay storage
    if mc ls --recursive "$QUAY_ALIAS/quaybucket/datastorage/registry/sha256/" | head -5 >/dev/null 2>&1; then
        print_success "Quay storage contains image blobs"
    else
        print_failure "No blobs found in Quay storage after image push"
        return 1
    fi
}

cleanup_test_data() {
    print_test "Cleaning up test data"
    
    # Remove backup bucket contents (let tool create bucket as needed)
    mc rm --recursive --force "$BACKUP_ALIAS/$TEST_BUCKET" >/dev/null 2>&1 || true
    
    # Clean up container images locally
    for image in "${TEST_IMAGES[@]}"; do
        local image_name=$(echo "$image" | cut -d'/' -f3 | cut -d':' -f1)
        local image_tag=$(echo "$image" | cut -d':' -f2)
        local quay_image="$QUAY_SERVER/$TEST_NAMESPACE/$image_name:$image_tag"
        $CONTAINER_RUNTIME rmi "$image" "$quay_image" >/dev/null 2>&1 || true
    done
    
    # Remove test repositories from Quay (but keep namespace for reuse)
    for image in "${TEST_IMAGES[@]}"; do
        local image_name=$(echo "$image" | cut -d'/' -f3 | cut -d':' -f1)
        curl -s -X DELETE \
            -u "$QUAY_USERNAME:$QUAY_PASSWORD" \
            "http://$QUAY_SERVER/api/v1/repository/$TEST_NAMESPACE/$image_name" >/dev/null 2>&1 || true
    done
    
    print_success "Cleaned up test data"
}

reset_environment() {
    print_test "Resetting test environment"
    increment_test
    
    cleanup_test_data
    verify_buckets_exist
    setup_test_data
    
    print_success "Reset test environment"
}

test_backup_basic() {
    print_header "Testing Basic Backup Operations"
    
    reset_environment
    
    print_test "Testing basic backup without force"
    increment_test
    if quaybkp --bucket-name "$TEST_BUCKET" backup "$TEST_NAMESPACE"  | grep -q "Operation.*Backup"; then
        print_success "Basic backup completed"
    else
        print_failure "Basic backup failed"
    fi
    
    print_test "Verifying backup inventory exists"
    increment_test
    if mc ls "$BACKUP_ALIAS/$TEST_BUCKET/$TEST_NAMESPACE/backup/" | grep -q "\.json"; then
        print_success "Backup inventory file created"
    else
        print_failure "Backup inventory file not found"
    fi
    
    print_test "Testing backup with force option"
    increment_test
    if quaybkp --bucket-name "$TEST_BUCKET" backup --force-blobs "$TEST_NAMESPACE" | grep -q "Operation.*Backup"; then
        print_success "Force backup completed"
    else
        print_failure "Force backup failed"
    fi
    
    print_test "Testing backup with custom worker count"
    increment_test
    if quaybkp --bucket-name "$TEST_BUCKET" backup  --num-workers 2 "$TEST_NAMESPACE" | grep -q "Operation.*Backup"; then
        print_success "Backup with custom workers completed"
    else
        print_failure "Backup with custom workers failed"
    fi
}

test_backup_edge_cases() {
    print_header "Testing Backup Edge Cases"
    
    print_test "Testing backup of non-existent namespace"
    increment_test
    if quaybkp --bucket-name "$TEST_BUCKET" backup "nonexistent" 2>&1 | grep -q "not found"; then
        print_success "Non-existent namespace handled correctly"
    else
        print_failure "Non-existent namespace not handled correctly"
    fi
    
    print_test "Testing concurrent backup protection (lock)"
    increment_test
    # Create a lock file manually
    echo "" | mc pipe "$BACKUP_ALIAS/$TEST_BUCKET/$TEST_NAMESPACE/backup/lock" >/dev/null 2>&1
    
    if quaybkp --bucket-name "$TEST_BUCKET" backup "$TEST_NAMESPACE" 2>&1 | grep -q "in progress"; then
        print_success "Backup lock protection works"
        # Clean up lock
        mc rm "$BACKUP_ALIAS/$TEST_BUCKET/$TEST_NAMESPACE/backup/lock" >/dev/null 2>&1
    else
        print_failure "Backup lock protection failed"
        mc rm "$BACKUP_ALIAS/$TEST_BUCKET/$TEST_NAMESPACE/backup/lock" >/dev/null 2>&1 || true
    fi
}

test_restore_basic() {
    print_header "Testing Basic Restore Operations"
    
    # Ensure we have a backup to restore from
    quaybkp --bucket-name "$TEST_BUCKET" backup "$TEST_NAMESPACE" >/dev/null 2>&1
    
    # Clear Quay storage to test restore
    mc rm --recursive --force "$QUAY_ALIAS/quaybucket/datastorage/" >/dev/null 2>&1 || true
    
    print_test "Testing basic restore"
    increment_test
    if quaybkp --bucket-name "$TEST_BUCKET" restore "$TEST_NAMESPACE" | grep -q "Operation.*Restore"; then
        print_success "Basic restore completed"
    else
        print_failure "Basic restore failed"
    fi
    
    print_test "Testing restore dry-run"
    increment_test
    if quaybkp --bucket-name "$TEST_BUCKET" restore --dry-run "$TEST_NAMESPACE" | grep -q "Dry Run"; then
        print_success "Restore dry-run completed"
    else
        print_failure "Restore dry-run failed"
    fi
    
    print_test "Testing restore with force option"
    increment_test
    if quaybkp --bucket-name "$TEST_BUCKET" restore --force-blobs "$TEST_NAMESPACE" | grep -q "Operation.*Restore"; then
        print_success "Force restore completed"
    else
        print_failure "Force restore failed"
    fi
    
    print_test "Testing restore with custom worker count"
    increment_test
    if quaybkp --bucket-name "$TEST_BUCKET"  restore --num-workers 3 "$TEST_NAMESPACE" | grep -q "Operation.*Restore"; then
        print_success "Restore with custom workers completed"
    else
        print_failure "Restore with custom workers failed"
    fi
}

test_restore_advanced() {
    print_header "Testing Advanced Restore Operations"
    
    # Ensure we have a backup
    quaybkp --bucket-name "$TEST_BUCKET" backup "$TEST_NAMESPACE" >/dev/null 2>&1
    
    print_test "Testing restore from specific backup number"
    increment_test
    if quaybkp --bucket-name "$TEST_BUCKET" restore --from 1  "$TEST_NAMESPACE" | grep -q "Operation.*Restore"; then
        print_success "Restore from specific backup completed"
    else
        print_failure "Restore from specific backup failed"
    fi
    
    print_test "Testing repository-specific restore"
    increment_test
    if quaybkp --bucket-name "$TEST_BUCKET" restore --repository "test-repo" "$TEST_NAMESPACE"  | grep -q "Operation.*Restore"; then
        print_success "Repository-specific restore completed"
    else
        print_failure "Repository-specific restore failed"
    fi
    
    print_test "Testing restore edge case - missing backup"
    increment_test
    if quaybkp --bucket-name "$TEST_BUCKET" restore --from 999 "$TEST_NAMESPACE"  2>&1 | grep -q "not found"; then
        print_success "Missing backup handled correctly"
    else
        print_failure "Missing backup not handled correctly"
    fi
}

test_verify_operations() {
    print_header "Testing Verify Operations"
    
    # Ensure we have a backup
    quaybkp --bucket-name "$TEST_BUCKET" backup "$TEST_NAMESPACE" >/dev/null 2>&1
    
    print_test "Testing basic verify"
    increment_test
    if quaybkp --bucket-name "$TEST_BUCKET" verify "$TEST_NAMESPACE" | grep -q "Operation.*Verify"; then
        print_success "Basic verify completed"
    else
        print_failure "Basic verify failed"
    fi
    
    print_test "Testing verify with specific backup number"
    increment_test
    if quaybkp --bucket-name "$TEST_BUCKET" verify --from 1 "$TEST_NAMESPACE" | grep -q "Operation.*Verify"; then
        print_success "Verify with specific backup completed"
    else
        print_failure "Verify with specific backup failed"
    fi
    
    print_test "Testing verify with missing backup"
    increment_test
    if quaybkp --bucket-name "$TEST_BUCKET" verify --from 999 "$TEST_NAMESPACE" 2>&1 | grep -q "not found"; then
        print_success "Verify missing backup handled correctly"
    else
        print_failure "Verify missing backup not handled correctly"
    fi
    
    #print_test "Testing verify with incomplete backup scenario"
    #increment_test
    # Add some blobs to Quay storage that aren't in backup
    # TODO: Refactor this to push another image into the namespace instead- this is a lousy hack
    #echo "extra blob" | mc pipe "$QUAY_ALIAS/quaybucket/datastorage/registry/sha256/99/99/999999999999999999999999999999999999999999999999999999999999999" >/dev/null 2>&1
    
    #if quaybkp --bucket-name "$TEST_BUCKET" verify "$TEST_NAMESPACE" | grep -q "Incomplete"; then
    #    print_success "Incomplete backup verification works"
    #else
    #    print_failure "Incomplete backup verification failed"
    #fi
}

test_unlock_operations() {
    print_header "Testing Unlock Operations"
    
    print_test "Testing unlock when no lock exists"
    increment_test
    if quaybkp --bucket-name "$TEST_BUCKET" unlock "$TEST_NAMESPACE" | grep -q "No backup lock found"; then
        print_success "Unlock with no lock handled correctly"
    else
        print_failure "Unlock with no lock not handled correctly"
    fi
    
    print_test "Testing unlock when lock exists"
    increment_test
    # Create a lock file
    echo "" | mc pipe "$BACKUP_ALIAS/$TEST_BUCKET/$TEST_NAMESPACE/backup/lock" >/dev/null 2>&1
    
    if quaybkp --bucket-name "$TEST_BUCKET" unlock "$TEST_NAMESPACE" | grep -q "Successfully removed"; then
        print_success "Unlock with existing lock works"
    else
        print_failure "Unlock with existing lock failed"
    fi
    
    print_test "Verifying lock was actually removed"
    increment_test
    if mc stat "$BACKUP_ALIAS/$TEST_BUCKET/$TEST_NAMESPACE/backup/lock" >/dev/null 2>&1; then
        print_failure "Lock file was not removed"       
    else
        print_success "Lock file was successfully removed"
    fi
}

test_error_handling() {
    print_header "Testing Error Handling"
    
    print_test "Testing invalid environment variables"
    increment_test
    # Temporarily break the S3 config
    local old_endpoint="$S3_ENDPOINT_URL"
    export S3_ENDPOINT_URL="http://invalid-host:9999"
    
    if quaybkp --bucket-name "$TEST_BUCKET" backup "$TEST_NAMESPACE" 2>&1 | grep -q -i "error\|fail"; then
        print_success "Invalid S3 endpoint handled correctly"
    else
        print_failure "Invalid S3 endpoint not handled correctly"
    fi
    
    # Restore environment
    export S3_ENDPOINT_URL="$old_endpoint"
    
    print_test "Testing missing Quay config"
    increment_test
    local old_config="$QUAY_CONFIG"
    export QUAY_CONFIG="/nonexistent/config.yaml"
    
    if quaybkp --bucket-name "$TEST_BUCKET" backup "$TEST_NAMESPACE" 2>&1 | grep -q -i "error\|not found"; then
        print_success "Missing Quay config handled correctly"
    else
        print_failure "Missing Quay config not handled correctly"
    fi
    
    # Restore environment
    export QUAY_CONFIG="$old_config"
}

test_stress_scenarios() {
    print_header "Testing Stress Scenarios"
    
    print_test "Testing multiple rapid backup attempts"
    increment_test
    local success_count=0
    for i in {1..3}; do
        if quaybkp --bucket-name "$TEST_BUCKET" backup "$TEST_NAMESPACE" >/dev/null 2>&1; then
            success_count=$((success_count + 1))
        fi
    done
    
    if [ $success_count -ge 2 ]; then
        print_success "Multiple rapid backups handled correctly"
    else
        print_failure "Multiple rapid backups failed"
    fi
    
    print_test "Testing backup with corrupted bucket state"
    increment_test
    # Create invalid backup inventory
    echo "invalid json content" | mc pipe "$BACKUP_ALIAS/$TEST_BUCKET/$TEST_NAMESPACE/backup/999.json" >/dev/null 2>&1
    
    if quaybkp --bucket-name "$TEST_BUCKET" backup "$TEST_NAMESPACE" >/dev/null 2>&1; then
        print_success "Backup with corrupted state handled"
    else
        print_failure "Backup with corrupted state failed"
    fi
    
    # Clean up corrupted file
    mc rm "$BACKUP_ALIAS/$TEST_BUCKET/$TEST_NAMESPACE/backup/999.json" >/dev/null 2>&1 || true
}

# Main test execution
main() {
    print_header "Quay Blob Backup and Restore Tool - Test Suite"
    
    # Initialize log file
    echo "Test run started at $(date)" > "$LOG_FILE"
    
    # Check prerequisites
    check_command_exists "mc"
    check_command_exists "python"
    check_command_exists "$CONTAINER_RUNTIME"
    check_command_exists "curl"
    
    # Setup
    setup_minio_aliases
    verify_buckets_exist
    setup_test_data
    
    # Run all tests
    test_backup_basic
    test_backup_edge_cases
    test_restore_basic
    test_restore_advanced
    test_verify_operations
    test_unlock_operations
    test_error_handling
    test_stress_scenarios
    
    # Final cleanup
    cleanup_test_data
    
    # Print results
    print_header "Test Results Summary"
    echo -e "${BLUE}Total Tests: $TOTAL_TESTS${NC}"
    echo -e "${GREEN}Passed: $PASSED_TESTS${NC}"
    echo -e "${RED}Failed: $FAILED_TESTS${NC}"
    
    if [ $FAILED_TESTS -eq 0 ]; then
        echo -e "${GREEN}All tests passed!${NC}"
        log "All tests passed!"
        exit 0
    else
        echo -e "${RED}Some tests failed. Check $LOG_FILE for details.${NC}"
        log "Some tests failed."
        exit 1
    fi
}

# Run main function with all arguments
main "$@"