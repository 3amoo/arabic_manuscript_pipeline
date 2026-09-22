"""
Input Handler Module
Automatically discovers and loads PDF/images from input directory.
"""

from pathlib import Path
from typing import List, Dict, Any
import pymupdf as fitz
from PIL import Image
import logging

logger = logging.getLogger(__name__)


class InputHandler:
    """Handles input file discovery and loading."""
    
    def __init__(self, input_dir: str = "data/input"):
        """
        Initialize InputHandler.

        Args:
            input_dir: Directory to search for input files
        """
        self.input_dir = Path(input_dir)
        self.input_dir.mkdir(parents=True, exist_ok=True)
        
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
    
    def load_file(self, file_path: Path, dpi: int = 300,
                  start_page: int = None,
                  end_page: int = None) -> List[Dict[str, Any]]:
        """
        Load a single file and extract pages/images.
        
        Args:
            file_path: Path to the file
            dpi: Resolution for PDF conversion
            start_page: 1-indexed first page to render (PDF only; pages
                before this are skipped at RENDER time, not filtered out
                after - rendering them just to throw the pixels away is
                the dominant memory cost on a long book). None = from the
                first page.
            end_page: 1-indexed last page to render (inclusive). None = to
                the last page.
        
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
        pages = loader(file_path, dpi, start_page=start_page, end_page=end_page)
        
        logger.info(f"Loaded {len(pages)} pages from {file_path.name}")
        
        return pages
    
    def _load_pdf(self, file_path: Path, dpi: int,
                  start_page: int = None,
                  end_page: int = None) -> List[Dict[str, Any]]:
        """Load PDF and convert pages to images.

        start_page/end_page (both 1-indexed and inclusive, either may be
        None) bound what gets RENDERED, not just what gets returned - a
        300-page book at 200 DPI is ~2.4 GB of pixel data, so skipping
        the render for out-of-range pages is the point, not an
        afterthought."""
        pages = []
        
        try:
            doc = fitz.open(file_path)
            logger.info(f"PDF has {len(doc)} pages")

            for page_num in range(len(doc)):
                one_indexed = page_num + 1
                # Bounds checks are deliberately on the render loop, not
                # a post-filter: the pixels never exist if they're not
                # needed. `break` (not `continue`) for the upper bound
                # since pages are ordered.
                if start_page is not None and one_indexed < start_page:
                    continue
                if end_page is not None and one_indexed > end_page:
                    break

                page = doc[page_num]

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

                # The embedded text-layer shortcut was retired (a broken
                # ToUnicode CMap produces well-formed-but-position-permuted
                # Arabic that passes any codepoint/ratio check). For
                # `لمعة النسب.pdf` the corruption is an anagrammatic
                # ligature-order defect that IS repairable (spec 021), but
                # the repaired text is still only fit as a cross-check, not
                # as an OCR replacement. PDF pages therefore always go
                # through the render -> preprocess -> layout -> OCR path.
                # Kept as an explicit key (not omitted) so every page dict
                # has the same shape regardless of loader.
                page_data = {
                    'page_num': page_num + 1,
                    'image': img_data,
                    'width': pix.width,
                    'height': pix.height,
                    'source_file': file_path.name,
                    'direct_text': None,
                    'metadata': {
                        'rotation': page.rotation,
                        'rect': list(page.rect),
                    }
                }
                
                pages.append(page_data)
                
                if (page_num + 1) % 10 == 0:
                    logger.info(f"  Processed {page_num + 1}/{len(doc)} pages")

            doc.close()
            
        except Exception as e:
            logger.error(f"Error loading PDF {file_path}: {e}")
            raise
        
        return pages
    
    def _load_image(self, file_path: Path, dpi: int,
                    start_page: int = None,
                    end_page: int = None) -> List[Dict[str, Any]]:
        """Load image file. The page-range arguments exist only for
        signature parity with _load_pdf (both are called through the same
        supported_formats dispatch table) - a single image is always page
        1, so any range not covering page 1 yields no pages."""
        pages = []
        
        try:
            # Open with PIL and normalize to RGB before any further processing.
            # Handles grayscale, RGBA, palette, 1-bit, and any other PIL mode.
            img = Image.open(file_path).convert("RGB")
            
            # Convert to numpy array and from RGB to BGR (OpenCV format)
            import numpy as np
            import cv2
            img_array = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

            if start_page is not None and 1 < start_page:
                logger.info(
                    f"  Image file is a single page - requested "
                    f"start_page={start_page} skips it entirely"
                )
                return pages
            if end_page is not None and end_page < 1:
                logger.info(
                    f"  Image file is a single page - requested "
                    f"end_page={end_page} skips it entirely"
                )
                return pages

            page_data = {
                'page_num': 1,
                'image': img_array,
                'width': img.width,
                'height': img.height,
                'source_file': file_path.name,
                # No PDF text layer support for plain image files - always
                # OCR. Kept as an explicit key (not omitted) so every page
                # dict has the same shape regardless of loader.
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
            except Exception:
                info['pages'] = None
        
        return info