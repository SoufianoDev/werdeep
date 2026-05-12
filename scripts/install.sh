#!/bin/bash
# WeRDeep Installation Script
# Supports both global and local installation modes

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Print colored message
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Check if pip is available
check_pip() {
    if ! command -v pip &> /dev/null && ! command -v pip3 &> /dev/null; then
        print_error "pip is not installed. Please install Python 3.11+ first."
        exit 1
    fi
}

# Install dependencies
install_dependencies() {
    print_info "Installing dependencies..."
    
    # Install Python dependencies
    if command -v pip &> /dev/null; then
        pip install -e .
    else
        pip3 install -e .
    fi
    
    # Install TypeScript dependencies if package.json exists
    if [ -f "package.json" ]; then
        print_info "Installing TypeScript dependencies..."
        
        if command -v bun &> /dev/null; then
            bun install
        elif command -v npm &> /dev/null; then
            npm install
        else
            print_warning "Neither bun nor npm found. Skipping TypeScript dependencies."
        fi
    fi
}

# Global installation
install_global() {
    print_info "Installing WeRDeep globally..."
    
    check_pip
    
    # Install globally
    if command -v pip &> /dev/null; then
        pip install -e .
    else
        pip3 install -e .
    fi
    
    # Verify installation
    if command -v werdeep &> /dev/null; then
        print_info "WeRDeep installed successfully!"
        werdeep --help
    else
        print_error "Installation failed. werdeep command not found in PATH."
        exit 1
    fi
}

# Local installation
install_local() {
    print_info "Installing WeRDeep locally in current directory..."
    
    check_pip
    
    # Get current directory
    PROJECT_DIR=$(pwd)
    
    print_info "Project directory: $PROJECT_DIR"
    
    # Install in development mode
    if command -v pip &> /dev/null; then
        pip install -e .
    else
        pip3 install -e .
    fi
    
    # Create local entry script
    mkdir -p bin
    cat > bin/werdeep <<EOF
#!/bin/bash
# Local WeRDeep entry point
cd "$PROJECT_DIR"
python -m werdeep.cli.main "\$@"
EOF
    chmod +x bin/werdeep
    
    print_info "WeRDeep installed locally!"
    print_info "Add '$PROJECT_DIR/bin' to your PATH or use: ./bin/werdeep"
    
    # Test installation
    ./bin/werdeep --help
}

# Main installation logic
main() {
    echo "=========================================="
    echo "WeRDeep Installation Script"
    echo "=========================================="
    echo ""
    
    # Parse arguments
    GLOBAL=false
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            --global|-g)
                GLOBAL=true
                shift
                ;;
            --local|-l)
                GLOBAL=false
                shift
                ;;
            --help|-h)
                echo "Usage: $0 [OPTIONS]"
                echo ""
                echo "Options:"
                echo "  --global, -g    Install globally (default)"
                echo "  --local, -l     Install locally in current directory"
                echo "  --help, -h      Show this help message"
                echo ""
                echo "Examples:"
                echo "  $0 --global     # Install globally"
                echo "  $0              # Install locally"
                exit 0
                ;;
            *)
                print_error "Unknown option: $1"
                echo "Run '$0 --help' for usage information."
                exit 1
                ;;
        esac
    done
    
    # Check if we're in the werdeep directory
    if [ ! -f "pyproject.toml" ]; then
        print_error "pyproject.toml not found. Please run this script from the WeRDeep root directory."
        exit 1
    fi
    
    # Perform installation
    if [ "$GLOBAL" = true ]; then
        install_global
    else
        install_local
    fi
    
    echo ""
    echo "=========================================="
    print_info "Installation complete!"
    echo "=========================================="
}

# Run main function
main "$@"
