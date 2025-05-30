# dependencies.py - Dependency checking and setup
import sys
import os
import subprocess
import platform
import shutil
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class DependencyChecker:
    """Check and manage system dependencies."""
    
    def __init__(self):
        self.python_version = sys.version_info
        self.platform = platform.system()
        self.issues = []
        self.warnings = []
    
    def check_all(self) -> bool:
        """Check all dependencies and return True if all are satisfied."""
        logger.info("=== Checking Dependencies ===")
        
        # Check Python version
        self._check_python_version()
        
        # Check Python packages
        self._check_python_packages()
        
        # Check oiiotool
        self._check_oiiotool()
        
        # Check required files
        self._check_required_files()
        
        # Check required folders
        self._check_required_folders()
        
        # Report issues
        if self.issues:
            logger.error("\nCritical issues found:")
            for issue in self.issues:
                logger.error(f"  ✗ {issue}")
            return False
        
        if self.warnings:
            logger.warning("\nWarnings:")
            for warning in self.warnings:
                logger.warning(f"  ⚠ {warning}")
        
        logger.info("\n✓ All dependencies satisfied!")
        return True
    
    def _check_python_version(self):
        """Check Python version meets requirements."""
        if self.python_version.major < 3 or (self.python_version.major == 3 and self.python_version.minor < 6):
            self.issues.append(
                f"Python 3.6+ required, found {self.python_version.major}.{self.python_version.minor}"
            )
        else:
            logger.info(f"✓ Python {self.python_version.major}.{self.python_version.minor}.{self.python_version.micro}")
    
    def _check_python_packages(self):
        """Check required Python packages."""
        required = {
            'PIL': 'Pillow',
            'numpy': 'numpy',
            'tqdm': 'tqdm',
            'yaml': 'PyYAML'
        }
        
        missing = []
        for import_name, package_name in required.items():
            try:
                __import__(import_name)
                logger.info(f"✓ {package_name}")
            except ImportError:
                missing.append(package_name)
                logger.warning(f"✗ {package_name} not installed")
        
        if missing:
            self.warnings.append(
                f"Missing Python packages: {', '.join(missing)}. "
                f"Install with: pip install {' '.join(missing)}"
            )
    
    def _check_oiiotool(self):
        """Check if oiiotool is available."""
        if shutil.which('oiiotool'):
            try:
                result = subprocess.run(['oiiotool', '--version'], 
                                      capture_output=True, text=True)
                version = result.stdout.strip()
                logger.info(f"✓ OpenImageIO (oiiotool) - {version}")
            except:
                logger.info("✓ OpenImageIO (oiiotool) found")
        else:
            install_cmd = self._get_oiiotool_install_command()
            self.issues.append(
                f"OpenImageIO (oiiotool) not found. Install with: {install_cmd}"
            )
    
    def _get_oiiotool_install_command(self) -> str:
        """Get platform-specific oiiotool installation command."""
        if self.platform == "Darwin":  # macOS
            return "brew install openimageio"
        elif self.platform == "Linux":
            return "sudo apt-get install openimageio-tools"
        elif self.platform == "Windows":
            return "Download from https://github.com/OpenImageIO/oiio/releases"
        else:
            return "Check OpenImageIO documentation for your platform"
    
    def _check_required_files(self):
        """Check for required files."""
        # Get the stillgen package directory
        package_dir = os.path.dirname(os.path.abspath(__file__))
        static_dir = os.path.join(package_dir, 'static')
        
        required_files = [
            (os.path.join(static_dir, "config_template.ocio"), "OCIO config template"),
            (os.path.join(static_dir, "logo_image.png"), "Logo image"),
            (os.path.join(static_dir, "tool_image.png"), "Tool image"),
            (os.path.join(static_dir, "fonts", "monarcha-regular.ttf"), "Font file")
        ]
        
        for filepath, description in required_files:
            if os.path.exists(filepath):
                logger.info(f"✓ {description} ({os.path.basename(filepath)})")
            else:
                self.warnings.append(f"{description} not found: {filepath}")
    
    def _check_required_folders(self):
        """Check for required folders."""
        # These folders should exist at the script level (not in package)
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        required_folders = [
            "01_INPUT_STILLS",
            "02_DIT_CSV",
            "03_DIT_FbF",
            "04_LAB_ALE",
            "05_OUTPUT_STILLS"
        ]
        
        # Also check static folders in package
        package_dir = os.path.dirname(os.path.abspath(__file__))
        static_folders = [
            os.path.join(package_dir, "static", "lut_dir")
        ]
        
        missing_folders = []
        
        # Check script-level folders
        for folder in required_folders:
            folder_path = os.path.join(script_dir, folder)
            if os.path.exists(folder_path):
                logger.info(f"✓ {folder}/")
            else:
                missing_folders.append(folder)
        
        # Check static folders
        for folder_path in static_folders:
            if os.path.exists(folder_path):
                logger.info(f"✓ {os.path.relpath(folder_path)}/")
            else:
                folder_name = os.path.basename(folder_path)
                missing_folders.append(f"stillgen/static/{folder_name}")
        
        if missing_folders:
            self.warnings.append(
                f"Missing folders: {', '.join(missing_folders)}. "
                "They will be created if needed."
            )


def check_dependencies():
    """Main function to check all dependencies."""
    checker = DependencyChecker()
    return checker.check_all()


def setup_virtual_environment():
    """Setup a virtual environment with required packages."""
    logger.info("Setting up virtual environment...")
    
    try:
        # Create virtual environment
        subprocess.run([sys.executable, "-m", "venv", "venv"], check=True)
        
        # Determine pip path
        if platform.system() == "Windows":
            pip_path = os.path.join("venv", "Scripts", "pip")
        else:
            pip_path = os.path.join("venv", "bin", "pip")
        
        # Install required packages
        packages = ["Pillow", "numpy", "tqdm", "PyYAML"]
        subprocess.run([pip_path, "install"] + packages, check=True)
        
        logger.info("✓ Virtual environment setup complete")
        logger.info("\nActivate with:")
        if platform.system() == "Windows":
            logger.info("  .\\venv\\Scripts\\activate")
        else:
            logger.info("  source venv/bin/activate")
        
        return True
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to setup virtual environment: {e}")
        return False


def install_missing_packages(packages: list) -> bool:
    """Install missing Python packages."""
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install"] + packages)
        return True
    except subprocess.CalledProcessError:
        return False


def check_and_create_folders(folders: list) -> bool:
    """Check and create required folders."""
    created = []
    
    for folder in folders:
        if not os.path.exists(folder):
            try:
                Path(folder).mkdir(parents=True, exist_ok=True)
                created.append(folder)
            except Exception as e:
                logger.error(f"Failed to create folder {folder}: {e}")
                return False
    
    if created:
        logger.info(f"Created folders: {', '.join(created)}")
    
    return True


def download_font(font_url: str = "https://www.fontsquirrel.com/fonts/download/miso") -> bool:
    """Download the required font file."""
    logger.info("Downloading font file...")
    
    try:
        import urllib.request
        import zipfile
        import io
        
        # Download font archive
        response = urllib.request.urlopen(font_url)
        data = response.read()
        
        # Extract font file
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for filename in z.namelist():
                if filename.endswith('miso-regular.ttf'):
                    z.extract(filename, '.')
                    # Move to root directory
                    shutil.move(filename, 'monarcha-regular.ttf')
                    logger.info("✓ Font downloaded successfully")
                    return True
        
        logger.error("Font file not found in archive")
        return False
        
    except Exception as e:
        logger.error(f"Failed to download font: {e}")
        return False


def get_system_info() -> dict:
    """Get system information for debugging."""
    return {
        'platform': platform.platform(),
        'python_version': f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        'executable': sys.executable,
        'cpu_count': os.cpu_count(),
        'cwd': os.getcwd()
    }


def print_system_info():
    """Print system information."""
    info = get_system_info()
    logger.info("\n=== System Information ===")
    for key, value in info.items():
        logger.info(f"{key}: {value}")


if __name__ == "__main__":
    # Run dependency check
    logging.basicConfig(level=logging.INFO)
    print_system_info()
    check_dependencies()
