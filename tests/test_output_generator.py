import unittest
import tempfile
import hashlib
from pathlib import Path

from src.pipeline.output.output_generator import OutputGenerator, SEPARATOR


class TestOutputGenerator(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.out_dir = Path(self._tmpdir.name)

    def tearDown(self):
        self._tmpdir.cleanup()

    def _make_page_file(self, raw_dir: Path, page_num: int, text: str):
        raw_dir.mkdir(parents=True, exist_ok=True)
        filename = raw_dir / f'page_{page_num:03d}.txt'
        filename.write_text(
            f"# Page {page_num}\n# OCR Method: test\n\n{text}",
            encoding='utf-8',
        )

    def test_partial_run_preserves_prior_pages(self):
        gen = OutputGenerator({'base_directory': str(self.out_dir)})
        raw_dir = self.out_dir / 'doc' / 'raw_text'
        for i in range(1, 5):
            self._make_page_file(raw_dir, i, f'page{i}')
        gen.save_page('doc', {'page_num': 5, 'text': 'page5', 'ocr_method': 'test'})
        result = (self.out_dir / 'doc' / 'full_manuscript.txt').read_text(encoding='utf-8')
        self.assertIn('page1', result)
        self.assertIn('page2', result)
        self.assertIn('page3', result)
        self.assertIn('page4', result)
        self.assertIn('page5', result)
        self.assertLess(result.index('page1'), result.index('page2'))
        self.assertLess(result.index('page2'), result.index('page3'))
        self.assertLess(result.index('page3'), result.index('page4'))
        self.assertLess(result.index('page4'), result.index('page5'))

    def test_two_sequential_partial_runs(self):
        gen = OutputGenerator({'base_directory': str(self.out_dir)})
        raw_dir = self.out_dir / 'doc' / 'raw_text'
        for i in range(1, 4):
            self._make_page_file(raw_dir, i, f'page{i}')
        gen.save_page('doc', {'page_num': 4, 'text': 'page4', 'ocr_method': 'test'})
        result = (self.out_dir / 'doc' / 'full_manuscript.txt').read_text(encoding='utf-8')
        self.assertIn('page1', result)
        self.assertIn('page2', result)
        self.assertIn('page3', result)
        self.assertIn('page4', result)
        self.assertLess(result.index('page1'), result.index('page2'))
        self.assertLess(result.index('page2'), result.index('page3'))
        self.assertLess(result.index('page3'), result.index('page4'))

    def test_gap_pages_handled(self):
        gen = OutputGenerator({'base_directory': str(self.out_dir)})
        raw_dir = self.out_dir / 'doc' / 'raw_text'
        for i in [1, 2, 5, 7]:
            self._make_page_file(raw_dir, i, f'page{i}')
        gen.save_page('doc', {'page_num': 99, 'text': 'skip', 'ocr_method': 'test'})
        result = (self.out_dir / 'doc' / 'full_manuscript.txt').read_text(encoding='utf-8')
        self.assertIn('page1', result)
        self.assertIn('page2', result)
        self.assertIn('page5', result)
        self.assertIn('page7', result)
        self.assertIn('skip', result)
        self.assertIn('--- نهاية الصفحة ---', result)
        self.assertLess(result.index('page1'), result.index('page2'))
        self.assertLess(result.index('page2'), result.index('page5'))
        self.assertLess(result.index('page5'), result.index('page7'))
        self.assertLess(result.index('page7'), result.index('skip'))

    def test_single_page_no_separator(self):
        gen = OutputGenerator({'base_directory': str(self.out_dir)})
        raw_dir = self.out_dir / 'doc' / 'raw_text'
        self._make_page_file(raw_dir, 1, 'only')
        gen.save_page('doc', {'page_num': 1, 'text': 'only', 'ocr_method': 'test'})
        result = (self.out_dir / 'doc' / 'full_manuscript.txt').read_text(encoding='utf-8')
        self.assertIn('only', result)
        self.assertNotIn('--- نهاية الصفحة ---', result)

    def test_empty_raw_text_dir(self):
        with tempfile.TemporaryDirectory() as td1:
            base1 = Path(td1)
            gen1 = OutputGenerator({'base_directory': str(base1)})
            gen1.save_page('doc', {'page_num': 1, 'text': 'hello', 'ocr_method': 'test'})
            result1 = (base1 / 'doc' / 'full_manuscript.txt').read_text(encoding='utf-8')
            self.assertEqual(result1, 'hello')

        with tempfile.TemporaryDirectory() as td2:
            base2 = Path(td2)
            (base2 / 'doc' / 'raw_text').mkdir(parents=True)
            gen2 = OutputGenerator({'base_directory': str(base2)})
            gen2.save_page('doc', {'page_num': 1, 'text': 'hello', 'ocr_method': 'test'})
            result2 = (base2 / 'doc' / 'full_manuscript.txt').read_text(encoding='utf-8')
            self.assertEqual(result2, 'hello')

    def test_non_standard_files_ignored(self):
        gen = OutputGenerator({'base_directory': str(self.out_dir)})
        raw_dir = self.out_dir / 'doc' / 'raw_text'
        raw_dir.mkdir(parents=True)
        (raw_dir / 'page_ABC.txt').write_text('abc_content', encoding='utf-8')
        (raw_dir / 'page_01.txt').write_text('short_content', encoding='utf-8')
        self._make_page_file(raw_dir, 1, 'body_001')
        gen.save_page('doc', {'page_num': 99, 'text': 'trigger', 'ocr_method': 'test'})
        result = (self.out_dir / 'doc' / 'full_manuscript.txt').read_text(encoding='utf-8')
        self.assertIn('body_001', result)
        self.assertIn('trigger', result)
        self.assertNotIn('abc_content', result)
        self.assertNotIn('short_content', result)

    def test_empty_page_file_included(self):
        gen = OutputGenerator({'base_directory': str(self.out_dir)})
        raw_dir = self.out_dir / 'doc' / 'raw_text'
        raw_dir.mkdir(parents=True)
        (raw_dir / 'page_001.txt').write_text(
            '# Page 1\n# OCR Method: test\n\n', encoding='utf-8',
        )
        gen.save_page('doc', {'page_num': 2, 'text': 'real', 'ocr_method': 'test'})
        result = (self.out_dir / 'doc' / 'full_manuscript.txt').read_text(encoding='utf-8')
        self.assertIn('real', result)
        self.assertIn('--- نهاية الصفحة ---', result)
        self.assertLess(result.index('--- نهاية الصفحة ---'), result.index('real'))

    def test_atomic_write_no_partial_file(self):
        gen = OutputGenerator({'base_directory': str(self.out_dir)})
        raw_dir = self.out_dir / 'doc' / 'raw_text'
        self._make_page_file(raw_dir, 1, 'x')
        gen.save_page('doc', {'page_num': 1, 'text': 'x', 'ocr_method': 'test'})
        self.assertTrue((self.out_dir / 'doc' / 'full_manuscript.txt').exists())
        doc_dir = self.out_dir / 'doc'
        tmp_files = list(doc_dir.glob('*.txt.tmp')) + list(doc_dir.glob('.full_manuscript_*'))
        self.assertEqual(tmp_files, [])

    def test_no_temp_files_remain_after_rebuild(self):
        gen = OutputGenerator({'base_directory': str(self.out_dir)})
        raw_dir = self.out_dir / 'doc' / 'raw_text'
        for i in range(1, 4):
            self._make_page_file(raw_dir, i, f'page{i}')
        gen.save_page('doc', {'page_num': 1, 'text': 'updated', 'ocr_method': 'test'})
        gen.save_page('doc', {'page_num': 2, 'text': 'updated2', 'ocr_method': 'test'})
        gen.save_page('doc', {'page_num': 3, 'text': 'updated3', 'ocr_method': 'test'})
        doc_dir = self.out_dir / 'doc'
        all_files = [f.name for f in doc_dir.iterdir() if f.is_file()]
        hidden_or_tmp = [f for f in all_files if f.startswith('.') or f.endswith('.tmp')]
        self.assertEqual(hidden_or_tmp, [])
        self.assertEqual(all_files, ['full_manuscript.txt'])

    def test_repeated_rebuilds_not_corrupted(self):
        gen = OutputGenerator({'base_directory': str(self.out_dir)})
        raw_dir = self.out_dir / 'doc' / 'raw_text'
        for i in range(1, 6):
            self._make_page_file(raw_dir, i, f'page{i}')
        for i in range(1, 6):
            gen.save_page('doc', {'page_num': i, 'text': f'fresh{i}', 'ocr_method': 'test'})
        result = (self.out_dir / 'doc' / 'full_manuscript.txt').read_text(encoding='utf-8')
        for i in range(1, 6):
            self.assertIn(f'fresh{i}', result)
        self.assertNotIn('page1', result)
        self.assertNotIn('page5', result)
        separators = result.count(SEPARATOR.strip())
        self.assertEqual(separators, 4)

    def test_raw_text_files_unchanged_after_rebuild(self):
        gen = OutputGenerator({'base_directory': str(self.out_dir)})
        raw_dir = self.out_dir / 'doc' / 'raw_text'
        for i in range(1, 6):
            self._make_page_file(raw_dir, i, f'page{i}')
        before = {}
        for i in range(1, 6):
            path = raw_dir / f'page_{i:03d}.txt'
            before[i] = hashlib.md5(path.read_bytes()).hexdigest()
        gen.save_page('doc', {'page_num': 6, 'text': 'new', 'ocr_method': 'test'})
        after = {}
        for i in range(1, 6):
            path = raw_dir / f'page_{i:03d}.txt'
            after[i] = hashlib.md5(path.read_bytes()).hexdigest()
        for i in range(1, 6):
            self.assertEqual(before[i], after[i])

    def test_current_run_overrides_disk(self):
        gen = OutputGenerator({'base_directory': str(self.out_dir)})
        raw_dir = self.out_dir / 'doc' / 'raw_text'
        raw_dir.mkdir(parents=True)
        (raw_dir / 'page_001.txt').write_text(
            '# Page 1\n# OCR Method: test\n\nold_version', encoding='utf-8',
        )
        gen.save_page('doc', {'page_num': 1, 'text': 'new_version', 'ocr_method': 'test'})
        result = (self.out_dir / 'doc' / 'full_manuscript.txt').read_text(encoding='utf-8')
        self.assertIn('new_version', result)
        self.assertNotIn('old_version', result)
