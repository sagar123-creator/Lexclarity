import unittest

from app.services.evidence import find_quote, _normalize

from tests.fakes import DatabaseTestCase


class FindQuoteTests(unittest.TestCase):
    def test_exact_match_after_whitespace_normalization(self):
        source = "The party shall pay  within thirty (30) days.\nSecond line here."
        quote = "party shall pay   within thirty (30) days"
        loc = find_quote(quote, source)
        self.assertTrue(loc.found)
        self.assertTrue(loc.exact)
        self.assertIsNotNone(loc.char_start)

    def test_fuzzy_match_tolerates_ocr_noise(self):
        source = "Client shall pay a monthly fee of $18,500 due within thirty days of invoice."
        quote = "Client shall pay a monthly fee of $18.500 due within thirty days of lnvoice."
        loc = find_quote(quote, source)
        self.assertTrue(loc.found)
        self.assertFalse(loc.exact)
        self.assertGreaterEqual(loc.match_ratio, 0.75)

    def test_not_found_when_quote_absent(self):
        source = "This agreement is governed by Massachusetts law."
        quote = "the service provider shall paint the office blue"
        loc = find_quote(quote, source)
        self.assertFalse(loc.found)

    def test_empty_inputs_not_found(self):
        self.assertFalse(find_quote("", "text").found)
        self.assertFalse(find_quote("quote", "").found)

    def test_quote_mapping_offsets_point_into_source(self):
        source = "alpha beta gamma delta epsilon"
        loc = find_quote("beta gamma", source)
        self.assertTrue(loc.found)
        self.assertEqual(source[loc.char_start:loc.char_end].strip(), "beta gamma")

    def test_normalize_unifies_quotes_and_whitespace(self):
        self.assertEqual(_normalize("a\u2019b  c"), _normalize("a'b c"))


class EvidenceDatabaseTests(DatabaseTestCase):
    def test_validate_finding_citation_accepts_real_quote(self):
        from app.services.evidence import validate_finding_citation

        doc = self.make_document()
        chunk = self.add_chunk(doc, "Either Party may terminate upon ninety (90) days prior written notice.")
        ok, start, end, note = validate_finding_citation(self.db, doc.id, chunk.id, "ninety (90) days prior written notice")
        self.assertTrue(ok)
        self.assertIsNotNone(start)
        self.assertIn("verified", note.lower())

    def test_validate_finding_citation_rejects_invented_quote(self):
        from app.services.evidence import validate_finding_citation

        doc = self.make_document()
        chunk = self.add_chunk(doc, "Either Party may terminate upon ninety (90) days notice.")
        ok, *_rest, note = validate_finding_citation(self.db, doc.id, chunk.id, "the office dog shall be walked daily")
        self.assertFalse(ok)
        self.assertIn("could not be located", note)

    def test_validate_finding_citation_rejects_missing_chunk(self):
        from app.services.evidence import validate_finding_citation

        doc = self.make_document()
        ok, *_rest, note = validate_finding_citation(self.db, doc.id, "no-such-chunk", "anything")
        self.assertFalse(ok)
        self.assertIn("does not exist", note)

    def test_build_citation_never_invents_page_numbers(self):
        from app.services.evidence import build_citation

        doc = self.make_document()
        self.add_chunk(doc, "some text", page=3)
        self.add_page(doc, "Page one of the contract.", page=1)

        # Citing a page that doesn't exist must NOT produce that page number.
        citation = build_citation(self.db, doc.id, chunk_id=None, page_number=99)
        self.assertIsNone(citation["page_number"])

        # Citing a real page works.
        citation = build_citation(self.db, doc.id, chunk_id=None, page_number=1)
        self.assertEqual(citation["page_number"], 1)

    def test_build_citation_rejects_cross_document_chunk(self):
        """A chunk id from another document must not be usable as a citation."""
        from app.services.evidence import build_citation

        doc_a = self.make_document(filename="a.txt")
        doc_b = self.make_document(filename="b.txt")
        chunk_a = self.add_chunk(doc_a, "confidentiality text from document A")

        citation = build_citation(self.db, doc_b.id, chunk_id=chunk_a.id)
        self.assertIsNone(citation["chunk_id"])  # chunk not in doc B -> dropped
        self.assertIsNone(citation["page_number"])


if __name__ == "__main__":
    unittest.main()
