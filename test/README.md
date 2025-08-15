# Quay Blob Backup and Restore Tool - Test Suite

This directory contains a comprehensive test suite for the `quaybkp` tool, designed to validate all functionality across different scenarios and performance characteristics.

## Test Structure

### Test Scripts

1. **`run_all_tests.sh`** - Master test runner that executes all test suites
2. **`test_framework.sh`** - Integration tests covering full CLI functionality
3. **`performance_tests.sh`** - Performance and scalability tests

### Configuration

- **`config/config.yaml`** - Test Quay configuration (DO NOT MODIFY)

## Prerequisites

Before running tests, ensure you have:

1. **MinIO Client (`mc`)** - For manipulating object storage
   ```bash
   # macOS
   brew install minio/stable/mc
   
   # Linux
   wget https://dl.min.io/client/mc/release/linux-amd64/mc
   chmod +x mc
   sudo mv mc /usr/local/bin/
   ```

2. **Container Runtime** - Docker or Podman for pulling and pushing test container images
   ```bash
   # Docker (default)
   docker --version
   
   # Or Podman (set CONTAINER_RUNTIME=podman)
   podman --version
   ```

3. **Python 3.8+** with required packages
   ```bash
   pip install -e ..  # Install quaybkp in development mode
   ```

4. **bc calculator** (for performance tests)
   ```bash
   # macOS
   brew install bc
   
   # Linux (usually pre-installed)
   sudo apt-get install bc  # Debian/Ubuntu
   sudo yum install bc      # CentOS/RHEL
   ```

5. **curl** - For Quay API interactions
   ```bash
   # Usually pre-installed on most systems
   curl --version
   ```

6. **Test Infrastructure**
   - Quay server running at `lab.local:8080`
   - Administrator account on Quay (credentials defined by QUAY_USERNAME, QUAY_PASSWORD)
   - Environment variable QUAYADMINTOKEN is set to [a valid OAuth2 token for Quay with Admin privileges](https://docs.redhat.com/en/documentation/red_hat_quay/3.15/html/red_hat_quay_api_guide/oauth2-access-tokens#creating-oauth-access-token) to create users
   - MinIO server running at `lab.local:9000` 
   - PostgreSQL database at `lab.local:5432`
   - Proper network connectivity to test endpoints
   - Docker registry access to `docker.io`

## Running Tests

### Quick Start

Run all tests:
```bash
cd test
# Using Docker (default)
./run_all_tests.sh

# Using Podman (with HTTP)
CONTAINER_RUNTIME=podman CONTAINER_TLS=--tls-verify=false ./run_all_tests.sh
```

### Selective Testing

Run specific test suites:
```bash
# Integration tests only  
./run_all_tests.sh --integration-only

# Performance tests only
./run_all_tests.sh --performance-only

# Skip performance tests
./run_all_tests.sh --no-performance

# Using Podman for any of the above (with HTTP)
CONTAINER_RUNTIME=podman CONTAINER_TLS=--tls-verify=false ./run_all_tests.sh --integration-only
```

### Individual Test Scripts

Run test scripts directly:
```bash
# Integration tests with Docker
./test_framework.sh

# Integration tests with Podman
CONTAINER_RUNTIME=podman ./test_framework.sh

# Performance tests with Docker
./performance_tests.sh

# Performance tests with Podman
CONTAINER_RUNTIME=podman ./performance_tests.sh
```

## Test Categories

### Integration Tests (`test_framework.sh`)

**Test Coverage:**
- Help command functionality
- Basic backup operations
- Backup edge cases (locks, non-existent namespaces)
- Basic restore operations  
- Advanced restore operations (specific backups, repository filters)
- Verify operations
- Unlock operations
- Error handling scenarios
- Stress testing

**Features Tested:**
- All CLI commands and options
- Lock management
- Concurrent operation protection
- Backup inventory generation
- Blob deduplication
- Force operations
- Dry-run mode
- Custom worker counts

### Performance Tests (`performance_tests.sh`)

**Performance Metrics:**
- Backup throughput (blobs per second)
- Restore throughput
- Verify operation speed
- Memory usage during operations
- Worker scaling efficiency
- Concurrent operation handling

**Scalability Testing:**
- Different container image counts (5, 10, 15)
- Variable worker counts (1, 3, 5, 10, 20)
- Memory usage profiling
- Scalability limits

## Test Environment

### Storage Configuration

Tests use the following storage setup:
- **Backup Storage**: MinIO at `lab.local:7000` (bucket: `quaybkp-test`)
- **Quay Storage**: MinIO at `lab.local:9000` (bucket: `quaybucket`)
- **Database**: PostgreSQL at `lab.local:5432`

### Test Data Management

- Tests use real container images pushed to Quay:
  - `docker.io/library/postgres:12.1`
  - `docker.io/library/redis:latest`
  - `docker.io/library/alpine:3.14`
  - `docker.io/library/busybox:1.34`
- Images are pulled from Docker Hub and pushed to test Quay instance
- Quay generates real blob storage from container image layers
- Tests automatically clean up test data via Quay API
- Each test suite uses isolated namespaces
- Environment reset between destructive tests
- Automatic cleanup on test completion

### Test Isolation

- Each test script is independent
- Environment variables scoped to test execution
- No persistent state between test runs
- Automatic resource cleanup

## Test Results

### Output Format

Tests provide colored output:
- 🟢 **Green**: Passed tests
- 🔴 **Red**: Failed tests  
- 🟡 **Yellow**: Test descriptions and warnings
- 🔵 **Blue**: Section headers and info

### Log Files

Test results are logged to:
- `test_results.log` - Integration test logs
- `performance_test_results.log` - Performance test logs with metrics

### Success Criteria

**Integration Tests:**
- All CLI commands execute successfully
- Proper error handling for edge cases
- Lock management works correctly
- Data integrity maintained across operations

**Performance Tests:**
- Backup/restore operations complete within reasonable time
- Worker scaling improves performance
- Memory usage stays within acceptable limits
- Concurrent operations properly handled

## Troubleshooting

### Common Issues

1. **MinIO Connection Failures**
   ```bash
   # Check MinIO connectivity
   mc alias set test http://lab.local:9000 miniouser miniopassword
   mc ls test/
   ```

2. **Database Connection Issues**
   ```bash
   # Test database connectivity
   psql -h lab.local -p 5432 -U quayuser -d quay -c "SELECT 1;"
   ```

3. **Permission Errors**
   ```bash
   # Ensure test scripts are executable
   chmod +x *.sh
   ```

4. **Package Installation Issues**
   ```bash
   # Reinstall quaybkp in development mode
   cd ..
   pip install -e .
   ```

### Test Debugging

Enable verbose output:
```bash
# Run with debug logging
PYTHONPATH=.. python -m quaybkp.main --log-level DEBUG backup testns
```

Check individual components:
```bash
# Test configuration loading
python3 -c "
import sys; sys.path.insert(0, '..')
from quaybkp.config.settings import Config
config = Config()
print('Config loaded successfully')
print('DB URI:', config.database_uri)
"
```

### Environment Variables

The test suite sets these automatically:
```bash
export QUAY_CONFIG="test/config/config.yaml"
export S3_ACCESS_KEY_ID="miniouser"
export S3_SECRET_ACCESS_KEY="miniopassword"
export S3_ENDPOINT_URL="http://lab.local:7000"
```

Optional environment variables:
```bash
# Container runtime selection (defaults to docker)
export CONTAINER_RUNTIME="podman"  # or "docker"
export CONTAINER_TLS="--tls-verify=false" # if using podman with HTTP
```

## Contributing

When adding new tests:

1. **Follow naming conventions**: `test_<functionality>.sh`
2. **Include cleanup**: Always clean up test data
3. **Add to master runner**: Update `run_all_tests.sh` if needed
4. **Document coverage**: Update this README with new test coverage
5. **Test isolation**: Ensure tests don't interfere with each other

### Test Script Template

```bash
#!/bin/bash
set -e

# Test configuration
TEST_DIR="$(dirname "$0")"
# ... setup code ...

# Test function
test_new_functionality() {
    print_test "Testing new functionality"
    increment_test
    
    # Test implementation
    if command_to_test; then
        print_success "New functionality works"
    else
        print_failure "New functionality failed"
    fi
}

# Main execution
main() {
    setup_environment
    test_new_functionality
    cleanup_environment
    print_results
}

main "$@"
```