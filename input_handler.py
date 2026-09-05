"""
Input Handler Module
Automatically discovers and loads PDF/images from input directory.
"""

import os
from pathlib import Path
from typing import List, Dict, Any
import pymupdf as fitz
from PIL import Image
import logging

from pdf_text_extractor import extract_direct_text

logger = logging.getLogger(__name__)


class InputHandler:
    """Handles input file discovery and loading."""
    
    def __init__(self, input_dir: str = "input", enable_direct_text_extraction: bool = True):
        """
        Initialize InputHandler.
        
        Args:
            input_dir: Directory to search for input files
            enable_direct_text_extraction: when True (default), each PDF
                page is first checked for a usable embedded text layer
                via pdf_text_extractor.extract_direct_text() - if found,
                that page's 'direct_text' key is populated and main.py
                skips preprocessing/OCR for it entirely (see
                pdf_text_extractor.py's module docstring for the
                per-page reasoning and the conservative usability check).
                Set to False to disable the check and force every PDF
                page through the normal render+OCR path, e.g. if a
                manuscript's embedded text layer is known to be garbage
                and the per-page check is somehow still passing it.
        """
        self.input_dir = Path(input_dir)
        self.input_dir.mkdir(parents=True, exist_ok=True)
        self.enable_direct_text_extraction = enable_direct_text_extraction
        
        self.supported_formats = {
            '.pdf': self._load_pdf,
            '.jpg': self._load_image,
            '.jpeg': self._load_image,
            '.png': self._load_image,
            '.tiff': self._load_image,
            '.tif': self._load_image,
        }
    
    def find_all_files(self) -> List[Path]:
        """
        Automatically find all supported files in input directory.
        
        Returns:
            List of file paths
        """
        files = []
        for extension in self.supported_formats.keys():
            found = list(self.input_dir.glob(f"*{extension}"))
            found.extend(list(self.input_dir.glob(f"*{extension.upper()}")))
            files.extend(found)
        
        # Remove duplicates and sort
        files = sorted(list(set(files)))
        
        logger.info(f"Found {len(files)} files in {self.input_dir}")
        for f in files:
            logger.debug(f"  - {f.name}")
        
        return files
    
    def load_file(self, file_path: Path, dpi: int = 300) -> List[Dict[str, Any]]:
        """
        Load a single file and extract pages/images.
        
        Args:
            file_path: Path to the file
            dpi: Resolution for PDF conversion
        
        Returns:
            List of page dictionaries with metadata
        """
        file_path = Path(file_path)
        
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        extension = file_path.suffix.lower()
        
        if extension not in self.supported_formats:
            raise ValueError(f"Unsupported format: {extension}")
        
        logger.info(f"Loading file: {file_path.name}")
        
        # Use the appropriate loader
        loader = self.supported_formats[extension]
        pages = loader(file_path, dpi)
        
        logger.info(f"Loaded {len(pages)} pages from {file_path.name}")
        
        return pages
    
    def _load_pdf(self, file_path: Path, dpi: int) -> List[Dict[str, Any]]:
        """Load PDF and convert pages to images."""
        pages = []
        
        try:
            doc = fitz.open(file_path)
            logger.info(f"PDF has {len(doc)} pages")
            
            direct_text_count = 0

            for page_num in range(len(doc)):
                page = doc[page_num]

                # Direct text-layer check FIRST, before rendering - see
                # pdf_text_extractor.py's module docstring. This is a
                # per-page decision (not per-file): a single PDF can mix
                # digitally-authored pages with scanned image pages, so
                # every page gets its own independent check. Rendering
                # below still happens unconditionally either way (the
                # 'image' key is relied on uniformly downstream, and
                # rendering isn't the expensive step this check saves -
                # OCR/GPU time is), only main.py's OCR pass is skipped
                # for pages where this returns usable text.
                direct_text = None
                if self.enable_direct_text_extraction:
                    direct_text = extract_direct_text(page)
                    if direct_text:
                        direct_text_count += 1

                # Render page to image
                mat = fitz.Matrix(dpi / 72, dpi / 72)  # 72 is default PDF DPI
                pix = page.get_pixmap(matrix=mat)
                
                # Convert to numpy array
                import numpy as np
                img_data = np.frombuffer(pix.samples, dtype=np.uint8)
                img_data = img_data.reshape((pix.height, pix.width, pix.n))
                
                # Convert RGB to BGR if needed (OpenCV format)
                if pix.n == 3:
                    import cv2
                    img_data = cv2.cvtColor(img_data, cv2.COLOR_RGB2BGR)
                
                page_data = {
                    'page_num': page_num + 1,
                    'image': img_data,
                    'width': pix.width,
                    'height': pix.height,
                    'source_file': file_path.name,
                    'direct_text': direct_text,
                    'metadata': {
                        'rotation': page.rotation,
                        'rect': list(page.rect),
                    }
                }
                
                pages.append(page_data)
                
                if (page_num + 1) % 10 == 0:
                    logger.info(f"  Processed {page_num + 1}/{len(doc)} pages")

            if self.enable_direct_text_extraction and direct_text_count:
                logger.info(
                    f"  Direct text-layer extraction: {direct_text_count}/{len(doc)} "
                    f"page(s) will skip OCR entirely (usable embedded text found)."
                )

            doc.close()
            
        except Exception as e:
            logger.error(f"Error loading PDF {file_path}: {e}")
            raise
        
        return pages
    
    def _load_image(self, file_path: Path, dpi: int) -> List[Dict[str, Any]]:
        """Load image file."""
        pages = []
        
        try:
            # Open with PIL
            img = Image.open(file_path)
            
            # Convert to numpy array
            import numpy as np
            img_array = np.array(img)
            
            # Convert RGB to BGR if needed
            if len(img_array.shape) == 3 and img_array.shape[2] == 3:
                import cv2
                img_array = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
            
            page_data = {
                'page_num': 1,
                'image': img_array,
                'width': img.width,
                'height': img.height,
                'source_file': file_path.name,
                # No PDF text layer to speak of for a plain image file -
                # always OCR. Kept as an explicit key (not omitted) so
                # every page dict has the same shape regardless of loader,
                # and main.py's page_data.get('direct_text') check works
                # identically either way.
                'direct_text': None,
                'metadata': {
                    'format': img.format,
                    'mode': img.mode,
                }
            }
            
            pages.append(page_data)
            
        except Exception as e:
            logger.error(f"Error loading image {file_path}: {e}")
            raise
        
        return pages
    
    def get_file_info(self, file_path: Path) -> Dict[str, Any]:
        """Get information about a file."""
        file_path = Path(file_path)
        
        info = {
            'path': str(file_path),
            'name': file_path.name,
            'size': file_path.stat().st_size,
            'extension': file_path.suffix.lower(),
        }
        
        if file_path.suffix.lower() == '.pdf':
            try:
                doc = fitz.open(file_path)
                info['pages'] = len(doc)
                doc.close()
            except:
                info['pages'] = None
        
        return info