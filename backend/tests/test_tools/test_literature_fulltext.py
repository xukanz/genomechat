"""Tests for JATS XML -> plain text extraction.

No HTTP. The tail-preservation test is the important one: dropping an inline
element must not swallow the prose that follows it.
"""

from src.tools.literature._fulltext import MAX_XML_BYTES, jats_to_text


def _article(body: str) -> str:
    return f"<article><body>{body}</body></article>"


class TestStructure:
    def test_section_title_becomes_a_heading(self):
        xml = _article("<sec><title>Introduction</title><p>Hello.</p></sec>")
        result = jats_to_text(xml)
        assert "## Introduction" in result
        assert "Hello." in result

    def test_paragraphs_are_separated_by_blank_lines(self):
        xml = _article("<sec><p>First.</p><p>Second.</p></sec>")
        assert "First.\n\nSecond." in jats_to_text(xml)

    def test_nested_sections_both_render(self):
        xml = _article(
            "<sec><title>Outer</title><p>A.</p><sec><title>Inner</title><p>B.</p></sec></sec>"
        )
        result = jats_to_text(xml)
        assert "## Outer" in result and "## Inner" in result
        assert result.index("## Outer") < result.index("## Inner")

    def test_falls_back_to_abstract_when_body_absent(self):
        xml = "<article><front><abstract><p>Just an abstract.</p></abstract></front></article>"
        assert "Just an abstract." in jats_to_text(xml)


class TestTailPreservation:
    def test_text_after_a_dropped_inline_element_survives(self):
        # `tail` belongs to the parent's flow, not the dropped child's. Missing
        # this swallows the rest of every sentence containing a citation marker.
        xml = _article("<p>text <xref>1</xref> more</p>")
        result = jats_to_text(xml)
        assert "text" in result and "more" in result
        assert "1" not in result

    def test_tail_after_a_dropped_figure_survives(self):
        xml = _article("<p>Before <fig><caption>Fig 1</caption></fig> after.</p>")
        result = jats_to_text(xml)
        assert "Before" in result and "after." in result
        assert "Fig 1" not in result

    def test_multiple_dropped_children_in_one_paragraph(self):
        xml = _article("<p>A <xref>1</xref> B <xref>2</xref> C</p>")
        result = jats_to_text(xml)
        for token in ("A", "B", "C"):
            assert token in result


class TestDroppedSubtrees:
    def test_tables_are_dropped_entirely(self):
        xml = _article("<sec><p>Keep.</p><table-wrap><p>DROPME</p></table-wrap></sec>")
        result = jats_to_text(xml)
        assert "Keep." in result
        assert "DROPME" not in result

    def test_formulae_are_dropped(self):
        xml = _article("<p>Keep <disp-formula>x=y</disp-formula> end.</p>")
        result = jats_to_text(xml)
        assert "x=y" not in result
        assert "Keep" in result and "end." in result

    def test_reference_list_is_dropped(self):
        xml = _article("<sec><p>Body.</p></sec><ref-list><ref>Citation text</ref></ref-list>")
        result = jats_to_text(xml)
        assert "Body." in result
        assert "Citation text" not in result

    def test_mathml_namespaced_element_is_dropped(self):
        xml = (
            '<article xmlns:mml="http://www.w3.org/1998/Math/MathML"><body>'
            "<p>Value <mml:math><mml:mi>DROPME</mml:mi></mml:math> here.</p>"
            "</body></article>"
        )
        result = jats_to_text(xml)
        assert "DROPME" not in result
        assert "Value" in result and "here." in result


class TestNamespaces:
    def test_namespaced_body_still_parses(self):
        xml = (
            '<article xmlns="http://example.org/jats"><body>'
            "<sec><title>Methods</title><p>Text.</p></sec>"
            "</body></article>"
        )
        result = jats_to_text(xml)
        assert "## Methods" in result
        assert "Text." in result


class TestFailureModes:
    def test_malformed_xml_returns_empty_string(self):
        assert jats_to_text("<article><body><p>unclosed") == ""

    def test_empty_input_returns_empty_string(self):
        assert jats_to_text("") == ""
        assert jats_to_text("   ") == ""

    def test_oversized_document_is_refused_before_parsing(self):
        oversized = "<article><body><p>" + ("x" * MAX_XML_BYTES) + "</p></body></article>"
        assert jats_to_text(oversized) == ""

    def test_document_without_body_or_abstract_returns_empty(self):
        assert jats_to_text("<article><front><title>T</title></front></article>") == ""

    def test_whitespace_is_normalised(self):
        xml = _article("<p>lots     of\n\n\n   space</p>")
        assert jats_to_text(xml) == "lots of space"
