"""Unit tests for src.service.memory.redaction.

Over-redaction is preferred to under-redaction. Every pattern in `_PATTERNS`
must have at least one positive match test; where ambiguity exists we also add
a negative test so future tuning stays honest.
"""

from __future__ import annotations

from src.service.memory.redaction import _PATTERNS, redact


def test_no_hits_returns_input_unchanged():
    text = "User prefers violin plots over box plots."
    out, hits = redact(text)
    assert out == text
    assert hits == []


def test_empty_input_returns_empty():
    out, hits = redact("")
    assert out == ""
    assert hits == []


def test_aws_access_key_redacted():
    raw = "Please remove key AKIA" + "FAKETESTKEY12XYZ from the script."
    out, hits = redact(raw)
    assert "AKIA" + "FAKETESTKEY12XYZ" not in out
    assert "[REDACTED:aws_access_key]" in out
    assert any(h.pattern_name == "aws_access_key" for h in hits)


def test_anthropic_key_redacted():
    raw = "Token: sk-ant-apiXX-abcDEFghijKLmnoPQrstUVwxyz1234567890abcdef."
    out, hits = redact(raw)
    assert "sk-ant-" not in out
    assert any(h.pattern_name == "anthropic_key" for h in hits)


def test_openai_key_redacted():
    raw = "OPENAI_API_KEY=sk-abcdefghijklmnopqrstuvwxyz0123456789ABCD"
    out, hits = redact(raw)
    assert "sk-abcdefghijklmnopqrstuvwxyz0123456789ABCD" not in out
    assert any(h.pattern_name == "openai_key" for h in hits)


def test_jwt_redacted():
    raw = "Authorization: Bearer eyJhbGciOiJIUzI1NiIs.eyJzdWIiOiIxMjM0NTY3ODkwIn0.signature_part_abc123"
    out, hits = redact(raw)
    assert "eyJhbGc" not in out
    assert any(h.pattern_name == "jwt" for h in hits)


def test_private_key_redacted():
    raw = (
        "Here is the key:\n"
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "MIIEvAIBADANBgkqhkiG9w0BAQEFAASCBKYwggSiAgEAAoIBAQ...\n"
        "-----END RSA PRIVATE KEY-----\n"
        "(do not ship)"
    )
    out, hits = redact(raw)
    assert "MIIEv" not in out
    assert any(h.pattern_name == "private_key" for h in hits)


def test_email_redacted():
    raw = "Contact jane.doe@example.com about the cohort."
    out, hits = redact(raw)
    assert "jane.doe@example.com" not in out
    assert any(h.pattern_name == "email" for h in hits)


def test_us_phone_redacted():
    raw = "Call me at 415-555-0199 if urgent."
    out, hits = redact(raw)
    assert "415-555-0199" not in out
    assert any(h.pattern_name == "us_phone" for h in hits)


def test_ssn_redacted():
    raw = "Patient SSN 123-45-6789 is in the file."
    out, hits = redact(raw)
    assert "123-45-6789" not in out
    assert any(h.pattern_name == "ssn" for h in hits)


def test_mrn_like_redacted_case_insensitive():
    raw = "See mrn 123456 and also MRN#9876543210."
    out, hits = redact(raw)
    names = [h.pattern_name for h in hits]
    assert names.count("mrn_like") == 2
    assert "123456" not in out and "9876543210" not in out


def test_patient_id_redacted():
    raw = "patient_id 987654 was misclassified."
    out, hits = redact(raw)
    assert "987654" not in out
    assert any(h.pattern_name == "patient_id_like" for h in hits)


def test_overlapping_and_multiple_hits_preserved():
    raw = "Email: a@b.co, key: AKIA" + "FAKETESTKEY12XYZ, MRN: 123456"
    out, hits = redact(raw)
    pattern_names = {h.pattern_name for h in hits}
    assert {"email", "aws_access_key", "mrn_like"}.issubset(pattern_names)
    assert "a@b.co" not in out
    assert "AKIA" not in out


def test_negative_non_phi_text_not_redacted():
    # Biomedical prose that could resemble IDs but isn't:
    raw = "Study 2024 cohort N=1234 patients, p=0.042, OR 1.8 (95% CI 1.2-2.7)."
    out, hits = redact(raw)
    assert out == raw
    assert hits == []


def test_hits_contain_valid_spans_on_original_text():
    raw = "ping jane.doe@example.com now"
    out, hits = redact(raw)
    # Spans are relative to the ORIGINAL text, not the redacted output
    assert len(hits) == 1
    start, end = hits[0].span
    assert raw[start:end] == "jane.doe@example.com"
    assert "jane.doe@example.com" not in out


def test_every_pattern_has_a_positive_case_defined_here():
    # Sanity check: `_PATTERNS` keys must be covered by the tests above.
    # Update this set whenever a new pattern lands.
    covered = {
        "aws_access_key",
        "anthropic_key",
        "openai_key",
        "jwt",
        "private_key",
        "email",
        "us_phone",
        "ssn",
        "mrn_like",
        "patient_id_like",
    }
    assert set(_PATTERNS.keys()) == covered, (
        "Redaction test coverage out of sync. "
        f"Missing: {set(_PATTERNS.keys()) - covered}  Extra: {covered - set(_PATTERNS.keys())}"
    )
