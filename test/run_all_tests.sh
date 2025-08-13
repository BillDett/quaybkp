#!/bin/bash

# Master Test Runner for quaybkp
# Runs all test suites and provides comprehensive reporting

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m' # No Color

# Test configuration
TEST_DIR="$(dirname "$0")"
PROJECT_ROOT="$(dirname "$TEST_DIR")"

# Test suite results
INTEGRATION_RESULT=0
PERFORMANCE_RESULT=0

print_banner() {
    echo -e "${PURPLE}========================================${NC}"
    echo -e "${PURPLE}  QUAY BLOB BACKUP TOOL TEST SUITE     ${NC}"
    echo -e "${PURPLE}========================================${NC}"
    echo ""
}

print_section() {
    echo -e "${BLUE}----------------------------------------${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}----------------------------------------${NC}"
}

check_prerequisites() {
    print_section "Checking Prerequisites"
    
    local missing_tools=()
    local container_runtime="${CONTAINER_RUNTIME:-docker}"
    
    # Check for required commands
    if ! command -v python3 &> /dev/null; then
        missing_tools+=("python3")
    fi
    
    if ! command -v mc &> /dev/null; then
        missing_tools+=("mc (MinIO client)")
    fi
    
    if ! command -v bc &> /dev/null; then
        missing_tools+=("bc (calculator)")
    fi
    
    if ! command -v "$container_runtime" &> /dev/null; then
        missing_tools+=("$container_runtime (container runtime)")
    fi
    
    # Check for Python package
    if ! python3 -c "import sys; sys.path.insert(0, '$PROJECT_ROOT'); import quaybkp" 2>/dev/null; then
        echo -e "${YELLOW}Warning: quaybkp package not properly installed${NC}"
        echo "Installing in development mode..."
        cd "$PROJECT_ROOT"
        pip install -e . >/dev/null 2>&1 || {
            echo -e "${RED}Failed to install quaybkp package${NC}"
            exit 1
        }
        cd "$TEST_DIR"
    fi
    
    # Check environment variables
    local env_vars=("QUAY_CONFIG" "S3_ACCESS_KEY_ID" "S3_SECRET_ACCESS_KEY" "S3_ENDPOINT_URL")
    for var in "${env_vars[@]}"; do
        if [ -z "${!var}" ]; then
            echo -e "${YELLOW}Warning: $var not set (will be set by test scripts)${NC}"
        fi
    done
    
    if [ ${#missing_tools[@]} -ne 0 ]; then
        echo -e "${RED}Missing required tools:${NC}"
        printf '%s\n' "${missing_tools[@]}"
        echo ""
        echo "Please install missing tools and try again."
        exit 1
    fi
    
    echo -e "${GREEN}All prerequisites satisfied${NC}"
    echo -e "${BLUE}Using container runtime: $container_runtime${NC}"
    echo ""
}


run_integration_tests() {
    print_section "Running Integration Tests"
    
    if [ -f "$TEST_DIR/test_framework.sh" ]; then
        chmod +x "$TEST_DIR/test_framework.sh"
        if bash -x "$TEST_DIR/test_framework.sh"; then
            echo -e "${GREEN}Integration tests: PASSED${NC}"
            INTEGRATION_RESULT=0
        else
            echo -e "${RED}Integration tests: FAILED${NC}"
            INTEGRATION_RESULT=1
        fi
    else
        echo -e "${YELLOW}Integration tests: SKIPPED (script not found)${NC}"
        INTEGRATION_RESULT=0
    fi
    echo ""
}

run_performance_tests() {
    print_section "Running Performance Tests"
    
    if [ -f "$TEST_DIR/performance_tests.sh" ]; then
        chmod +x "$TEST_DIR/performance_tests.sh"
        if "$TEST_DIR/performance_tests.sh"; then
            echo -e "${GREEN}Performance tests: PASSED${NC}"
            PERFORMANCE_RESULT=0
        else
            echo -e "${RED}Performance tests: FAILED${NC}"
            PERFORMANCE_RESULT=1
        fi
    else
        echo -e "${YELLOW}Performance tests: SKIPPED (script not found)${NC}"
        PERFORMANCE_RESULT=0
    fi
    echo ""
}

generate_report() {
    print_section "Test Results Summary"
    
    # Calculate overall result
    local overall_result=$((INTEGRATION_RESULT + PERFORMANCE_RESULT))
    
    # Print individual results
    echo "Test Suite Results:"
    echo "==================="
    
    if [ $INTEGRATION_RESULT -eq 0 ]; then
        echo -e "Integration Tests: ${GREEN}PASSED${NC}"
    else
        echo -e "Integration Tests: ${RED}FAILED${NC}"
    fi
    
    if [ $PERFORMANCE_RESULT -eq 0 ]; then
        echo -e "Performance Tests: ${GREEN}PASSED${NC}"
    else
        echo -e "Performance Tests: ${RED}FAILED${NC}"
    fi
    
    echo ""
    
    # Print overall result
    if [ $overall_result -eq 0 ]; then
        echo -e "${GREEN}OVERALL RESULT: ALL TESTS PASSED${NC}"
        echo -e "${GREEN}✓ The quaybkp tool is ready for production use${NC}"
    else
        echo -e "${RED}OVERALL RESULT: SOME TESTS FAILED${NC}"
        echo -e "${RED}✗ Please review failed tests before using the tool${NC}"
    fi
    
    echo ""
    
    # Print log file locations
    echo "Test logs available at:"
    echo "======================"
    [ -f "$TEST_DIR/test_results.log" ] && echo "Integration Tests: $TEST_DIR/test_results.log"
    [ -f "$TEST_DIR/performance_test_results.log" ] && echo "Performance Tests: $TEST_DIR/performance_test_results.log"
    
    return $overall_result
}

show_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --integration-only Run only integration tests"
    echo "  --performance-only Run only performance tests"
    echo "  --no-performance  Skip performance tests"
    echo "  --help            Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0                    # Run all test suites"
    echo "  $0 --integration-only # Run only integration tests"
    echo "  $0 --no-performance  # Run integration tests only"
    echo ""
    echo "Environment Variables:"
    echo "  CONTAINER_RUNTIME     Container runtime to use (docker/podman, default: docker)"
}

# Main execution
main() {
    local run_integration=true
    local run_performance=true
    
    # Parse command line arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --integration-only)
                run_integration=true
                run_performance=false
                shift
                ;;
            --performance-only)
                run_integration=false
                run_performance=true
                shift
                ;;
            --no-performance)
                run_performance=false
                shift
                ;;
            --help)
                show_usage
                exit 0
                ;;
            *)
                echo "Unknown option: $1"
                show_usage
                exit 1
                ;;
        esac
    done
    
    print_banner
    
    # Record start time
    start_time=$(date +%s)
    
    # Check prerequisites
    check_prerequisites
    
    # Run selected test suites
    if [ "$run_integration" = true ]; then
        run_integration_tests
    else
        echo -e "${YELLOW}Integration tests: SKIPPED (by user request)${NC}"
        echo ""
    fi
    
    if [ "$run_performance" = true ]; then
        run_performance_tests
    else
        echo -e "${YELLOW}Performance tests: SKIPPED (by user request)${NC}"
        echo ""
    fi
    
    # Calculate total time
    end_time=$(date +%s)
    total_time=$((end_time - start_time))
    
    echo -e "${BLUE}Total test execution time: ${total_time} seconds${NC}"
    echo ""
    
    # Generate final report
    generate_report
}

# Run main function with all arguments
main "$@"