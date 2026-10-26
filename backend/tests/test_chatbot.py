"""Chatbot answering: retrieval gate, refusal behaviour and answer shaping."""
import unittest
from unittest.mock import patch

from app.config import settings
from app.services.chatbot import NOT_FOUND_ANSWER, answer_question

from tests.fakes import DatabaseTestCase, fake_llm, fake_retrieval

TERMINATION_CHUNK = (
    "The termination notice period is ninety (90) days. "
    "Either Party may end the agreement by giving written notice."
)


class ChatAnswerTests(DatabaseTestCase):
    def _setup_doc(self, text=TERMINATION_CHUNK, filename="contract.txt"):
        doc = self.make_document(filename=filename)
        chunk = self.add_chunk(doc, text, section="Termination")
        return doc, chunk

    def test_direct_answer_with_verified_citation(self):
        doc, chunk = self._setup_doc()
        response = {
            "confidence": "answered",
            "answer": "Ninety (90) days' written notice.",
            "citations": [{"page_number": 1, "section": "Termination", "chunk_id": chunk.id}],
        }
        with fake_retrieval() as store, fake_llm([response]) as calls:
            store.upsert_chunks(
                doc.id, [chunk.id], [TERMINATION_CHUNK], [None],
                [{"page_number": 1, "section_heading": "Termination"}],
            )
            result = answer_question(doc.id, "What is the termination notice period?", [])

        self.assertEqual(len(calls), 1)
        self.assertEqual(result["confidence"], "answered")
        self.assertEqual(result["answer"], "Ninety (90) days' written notice.")
        # Citation must resolve to a real retrieved chunk (never invented).
        self.assertTrue(result["citations"][0]["verified"])
        self.assertIn("termination notice period", result["citations"][0]["snippet"])

    def test_document_filename_is_passed_to_the_model(self):
        doc, chunk = self._setup_doc(filename="service_agreement.txt")
        response = {"confidence": "answered", "answer": "ok", "citations": []}
        with fake_retrieval() as store, fake_llm([response]) as calls:
            store.upsert_chunks(
                doc.id, [chunk.id], [TERMINATION_CHUNK], [None],
                [{"page_number": 1, "section_heading": "Termination"}],
            )
            answer_question(doc.id, "What is the termination notice period?", [],
                            document_name="service_agreement.txt")

        self.assertIn("service_agreement.txt", calls[0][1])

    def test_near_miss_passage_still_reaches_the_model(self):
        """Below the strict similarity bar the closest chunks must still be sent,
        otherwise short documents get a blanket 'not found' for valid questions."""
        doc, chunk = self._setup_doc()
        response = {"confidence": "answered", "answer": "Ninety days.", "citations": []}
        with fake_retrieval() as store, fake_llm([response]) as calls:
            store.upsert_chunks(
                doc.id, [chunk.id], [TERMINATION_CHUNK], [None],
                [{"page_number": 1, "section_heading": "Termination"}],
            )
            with patch.object(settings, "RETRIEVAL_MIN_SIMILARITY", 0.99):
                result = answer_question(doc.id, "What is the termination notice period?", [])

        self.assertEqual(len(calls), 1)
        self.assertEqual(result["confidence"], "answered")
        self.assertEqual(result["answer"], "Ninety days.")

    def test_unanswerable_question_never_calls_the_model(self):
        doc, chunk = self._setup_doc(text="Payments are due thirty days after invoice.")
        with fake_retrieval() as store, fake_llm([]) as calls:
            store.upsert_chunks(
                doc.id, [chunk.id], ["Payments are due thirty days after invoice."], [None],
                [{"page_number": 1, "section_heading": "Payment"}],
            )
            result = answer_question(doc.id, "What is the capital of France?", [])

        self.assertEqual(calls, [])
        self.assertEqual(result["confidence"], "not_found")
        self.assertEqual(result["answer"], NOT_FOUND_ANSWER)
        self.assertEqual(result["citations"], [])

    def test_refusal_asks_for_a_valid_document_question(self):
        self.assertIn("ask", NOT_FOUND_ANSWER.lower())
        self.assertIn("uploaded file", NOT_FOUND_ANSWER.lower())

    def test_model_declined_reply_is_returned_verbatim(self):
        """Off-topic questions are declined by the model itself, in its own words."""
        doc, chunk = self._setup_doc()
        response = {
            "confidence": "not_found",
            "answer": "This document is a service agreement and does not cover that. "
                      "Ask me about its termination or payment terms.",
            "citations": [],
        }
        with fake_retrieval() as store, fake_llm([response]):
            store.upsert_chunks(
                doc.id, [chunk.id], [TERMINATION_CHUNK], [None],
                [{"page_number": 1, "section_heading": "Termination"}],
            )
            result = answer_question(doc.id, "What is the capital of France?", [])

        self.assertEqual(result["confidence"], "not_found")
        self.assertIn("does not cover", result["answer"])
        self.assertIn("Ask me about", result["answer"])

    def test_empty_model_answer_falls_back_to_the_refusal(self):
        doc, chunk = self._setup_doc()
        response = {"confidence": "answered", "answer": "   ", "citations": []}
        with fake_retrieval() as store, fake_llm([response]):
            store.upsert_chunks(
                doc.id, [chunk.id], [TERMINATION_CHUNK], [None],
                [{"page_number": 1, "section_heading": "Termination"}],
            )
            result = answer_question(doc.id, "What is the termination notice period?", [])

        self.assertEqual(result["answer"], NOT_FOUND_ANSWER)

    def test_document_with_no_chunks_returns_not_found(self):
        doc = self.make_document()
        with fake_retrieval(), fake_llm([]) as calls:
            result = answer_question(doc.id, "What are the risks?", [])

        self.assertEqual(calls, [])
        self.assertEqual(result["confidence"], "not_found")


if __name__ == "__main__":
    unittest.main()
