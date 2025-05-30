# stillgen.py - Main entry point
import sys
import os
import argparse
import logging
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
from tqdm import tqdm
import multiprocessing

from dependencies import check_dependencies
from parsers import parse_ale_files, parse_silverstack_files, LazyCSVLoader
from image_processor import StillProcessor
from config import Config, ProcessingProfile
from utils import find_tiff_files, process_in_batches

# Set up logging
def setup_logging(verbose=False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('stillgen.log'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='StillGen - Film Still Processing Tool')
    
    # Required arguments
    parser.add_argument('input_folder', help='Input folder containing TIFF files')
    parser.add_argument('output_folder', help='Output folder for processed images')
    parser.add_argument('lut_dir', help='Directory containing LUT files')
    parser.add_argument('frame_csv_folder', help='Folder containing per-frame CSV files')
    parser.add_argument('lab_ale_folder', help='Folder containing lab ALE files')
    parser.add_argument('config_template', help='OCIO config template file')
    parser.add_argument('silverstack_csv_folder', help='Folder containing Silverstack CSV files')
    
    # Optional arguments
    parser.add_argument('--profile', choices=['preview', 'final'], default='final',
                        help='Processing profile (preview for faster processing)')
    parser.add_argument('--workers', type=int, default=None,
                        help='Number of worker processes (default: CPU count)')
    parser.add_argument('--batch-size', type=int, default=10,
                        help='Batch size for processing (default: 10)')
    parser.add_argument('--resume', action='store_true',
                        help='Resume processing (skip existing files)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Perform a dry run without processing')
    parser.add_argument('--verbose', action='store_true',
                        help='Enable verbose logging')
    parser.add_argument('--config-file', help='Optional configuration file (YAML/JSON)')
    
    return parser.parse_args()


def process_batch(batch_args):
    """Process a batch of images. Used for multiprocessing."""
    batch_files, config, ale_data, silverstack_data, csv_loader = batch_args
    results = []
    
    # Create processor for this batch
    processor = StillProcessor(config, ale_data, silverstack_data, csv_loader)
    
    for file_path in batch_files:
        try:
            success = processor.process_image(file_path)
            results.append((file_path, success, None))
        except Exception as e:
            results.append((file_path, False, str(e)))
    
    return results


def main():
    args = parse_arguments()
    logger = setup_logging(args.verbose)
    
    logger.info("=== StillGen Processing Started ===")
    
    # Check dependencies
    if not args.dry_run:
        logger.info("Checking dependencies...")
        check_dependencies()
    
    # Create configuration
    config = Config(
        input_folder=args.input_folder,
        output_folder=args.output_folder,
        lut_dir=args.lut_dir,
        frame_csv_folder=args.frame_csv_folder,
        lab_ale_folder=args.lab_ale_folder,
        config_template_path=args.config_template,
        silverstack_csv_folder=args.silverstack_csv_folder,
        profile=ProcessingProfile(args.profile),
        resume=args.resume
    )
    
    # Load configuration file if provided
    if args.config_file:
        config.load_from_file(args.config_file)
    
    # Load data
    logger.info("Loading ALE files...")
    ale_data = parse_ale_files(config.lab_ale_folder)
    logger.info(f"Loaded {len(ale_data)} clips from ALE files")
    
    logger.info("Loading Silverstack CSV files...")
    silverstack_data = parse_silverstack_files(config.silverstack_csv_folder)
    logger.info(f"Loaded {len(silverstack_data)} clips from Silverstack files")
    
    # Create lazy CSV loader
    csv_loader = LazyCSVLoader(config.frame_csv_folder)
    
    # Find all TIFF files
    logger.info("Scanning for TIFF files...")
    tiff_files = find_tiff_files(config.input_folder)
    
    # Filter out already processed files if resuming
    if config.resume:
        tiff_files = [f for f in tiff_files if not config.is_processed(f)]
        logger.info(f"Resuming: {len(tiff_files)} files remaining")
    else:
        logger.info(f"Found {len(tiff_files)} TIFF files to process")
    
    if args.dry_run:
        logger.info("DRY RUN - Files that would be processed:")
        for f in tiff_files[:10]:
            logger.info(f"  {f}")
        if len(tiff_files) > 10:
            logger.info(f"  ... and {len(tiff_files) more files")
        return
    
    # Process files
    processed = 0
    errors = []
    
    # Determine number of workers
    num_workers = args.workers or multiprocessing.cpu_count()
    logger.info(f"Using {num_workers} worker processes")
    
    # Process in batches
    batches = list(process_in_batches(tiff_files, args.batch_size))
    
    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        # Prepare batch arguments
        batch_args = [
            (batch, config, ale_data, silverstack_data, csv_loader)
            for batch in batches
        ]
        
        # Submit all batches
        future_to_batch = {
            executor.submit(process_batch, args): i
            for i, args in enumerate(batch_args)
        }
        
        # Process results with progress bar
        with tqdm(total=len(tiff_files), desc="Processing images") as pbar:
            for future in as_completed(future_to_batch):
                batch_idx = future_to_batch[future]
                try:
                    results = future.result()
                    for file_path, success, error in results:
                        if success:
                            processed += 1
                        else:
                            errors.append((file_path, error))
                        pbar.update(1)
                except Exception as e:
                    logger.error(f"Batch {batch_idx} failed: {str(e)}")
                    pbar.update(len(batches[batch_idx]))
    
    # Report results
    logger.info(f"\n=== Processing Complete ===")
    logger.info(f"Successfully processed: {processed}/{len(tiff_files)} files")
    
    if errors:
        logger.error(f"Errors encountered: {len(errors)}")
        for file_path, error in errors[:5]:
            logger.error(f"  {file_path}: {error}")
        if len(errors) > 5:
            logger.error(f"  ... and {len(errors) - 5} more errors")
    
    # Save processing report
    config.save_processing_report(processed, errors)


if __name__ == "__main__":
    main()
