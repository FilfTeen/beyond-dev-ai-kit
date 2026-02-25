"""Unit tests for pipeline_yaml_parser module."""

import sys
import os
import unittest

# Ensure tools directory is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from pipeline_yaml_parser import (
    ParseError,
    count_indent,
    unquote,
    split_top_level,
    split_key_value,
    parse_scalar,
    parse_cli_bool,
    strip_inline_comment,
    parse_simple_yaml_two_level,
    parse_inline_parameters,
    parse_yaml_step_block,
    extract_yaml_blocks,
)


class TestCountIndent(unittest.TestCase):
    def test_no_indent(self):
        self.assertEqual(count_indent("hello"), 0)

    def test_two_spaces(self):
        self.assertEqual(count_indent("  hello"), 2)

    def test_empty_line(self):
        self.assertEqual(count_indent(""), 0)

    def test_only_spaces(self):
        self.assertEqual(count_indent("    "), 4)


class TestUnquote(unittest.TestCase):
    def test_double_quoted(self):
        self.assertEqual(unquote('"hello"'), "hello")

    def test_single_quoted(self):
        self.assertEqual(unquote("'hello'"), "hello")

    def test_no_quotes(self):
        self.assertEqual(unquote("hello"), "hello")

    def test_mismatched_quotes(self):
        self.assertEqual(unquote("'hello\""), "'hello\"")

    def test_escaped_quote(self):
        self.assertEqual(unquote('"say \\"hi\\""'), 'say "hi"')


class TestSplitTopLevel(unittest.TestCase):
    def test_simple_csv(self):
        self.assertEqual(split_top_level("a, b, c"), ["a", "b", "c"])

    def test_nested_brackets(self):
        self.assertEqual(split_top_level("a, [b, c], d"), ["a", "[b, c]", "d"])

    def test_quoted_comma(self):
        self.assertEqual(split_top_level('a, "b, c", d'), ["a", '"b, c"', "d"])

    def test_empty(self):
        self.assertEqual(split_top_level(""), [])


class TestSplitKeyValue(unittest.TestCase):
    def test_simple(self):
        self.assertEqual(split_key_value("name: hello"), ("name", " hello"))

    def test_no_colon(self):
        self.assertEqual(split_key_value("nocolon"), (None, None))

    def test_colon_in_quotes(self):
        k, v = split_key_value('"key:with:colons": value')
        self.assertEqual(k, '"key:with:colons"')
        self.assertEqual(v, " value")


class TestParseScalar(unittest.TestCase):
    def test_bool_true(self):
        self.assertIs(parse_scalar("true"), True)

    def test_bool_false(self):
        self.assertIs(parse_scalar("false"), False)

    def test_null(self):
        self.assertIsNone(parse_scalar("null"))

    def test_integer(self):
        self.assertEqual(parse_scalar("42"), 42)

    def test_negative_integer(self):
        self.assertEqual(parse_scalar("-7"), -7)

    def test_float(self):
        self.assertEqual(parse_scalar("3.14"), 3.14)

    def test_empty_list(self):
        self.assertEqual(parse_scalar("[]"), [])

    def test_list(self):
        self.assertEqual(parse_scalar("[a, b]"), ["a", "b"])

    def test_string(self):
        self.assertEqual(parse_scalar("hello"), "hello")

    def test_quoted_string(self):
        self.assertEqual(parse_scalar('"hello"'), "hello")

    def test_empty(self):
        self.assertEqual(parse_scalar(""), "")


class TestParseCliBool(unittest.TestCase):
    def test_none_default_false(self):
        self.assertFalse(parse_cli_bool(None, default=False))

    def test_none_default_true(self):
        self.assertTrue(parse_cli_bool(None, default=True))

    def test_true_variants(self):
        for val in ("1", "true", "yes", "y", "on", "True", "YES"):
            self.assertTrue(parse_cli_bool(val), f"Failed for {val}")

    def test_false_variants(self):
        for val in ("0", "false", "no", "n", "off", "False", "NO"):
            self.assertFalse(parse_cli_bool(val), f"Failed for {val}")

    def test_bool_passthrough(self):
        self.assertTrue(parse_cli_bool(True))
        self.assertFalse(parse_cli_bool(False))

    def test_unknown_uses_default(self):
        self.assertFalse(parse_cli_bool("maybe", default=False))


class TestStripInlineComment(unittest.TestCase):
    def test_no_comment(self):
        self.assertEqual(strip_inline_comment("hello world"), "hello world")

    def test_with_comment(self):
        self.assertEqual(strip_inline_comment("hello # world"), "hello")

    def test_hash_in_quotes(self):
        self.assertEqual(strip_inline_comment('"hello # world"'), '"hello # world"')


class TestParseSimpleYamlTwoLevel(unittest.TestCase):
    def test_flat(self):
        text = "name: hello\nversion: 1"
        result = parse_simple_yaml_two_level(text)
        self.assertEqual(result["name"], "hello")
        self.assertEqual(result["version"], 1)

    def test_nested(self):
        text = "section:\n  key1: value1\n  key2: value2"
        result = parse_simple_yaml_two_level(text)
        self.assertEqual(result["section"]["key1"], "value1")

    def test_invalid_line(self):
        with self.assertRaises(ParseError):
            parse_simple_yaml_two_level("no colon here")


class TestParseInlineParameters(unittest.TestCase):
    def test_simple(self):
        result = parse_inline_parameters("mode: scan, target: db")
        self.assertEqual(result, {"mode": "scan", "target": "db"})

    def test_empty(self):
        result = parse_inline_parameters("")
        self.assertEqual(result, {})


class TestParseYamlStepBlock(unittest.TestCase):
    def test_inline_params(self):
        block = "skill: my_skill\nparameters: {mode: scan, target: db}"
        result = parse_yaml_step_block(block)
        self.assertEqual(result["skill"], "my_skill")
        self.assertEqual(result["parameters"]["mode"], "scan")

    def test_block_params(self):
        block = "skill: my_skill\nparameters:\n  mode: scan\n  target: db"
        result = parse_yaml_step_block(block)
        self.assertEqual(result["skill"], "my_skill")
        self.assertEqual(result["parameters"]["mode"], "scan")

    def test_missing_skill(self):
        with self.assertRaises(ParseError):
            parse_yaml_step_block("parameters: {mode: scan}")

    def test_missing_parameters(self):
        with self.assertRaises(ParseError):
            parse_yaml_step_block("skill: my_skill")


class TestExtractYamlBlocks(unittest.TestCase):
    def test_single_block(self):
        md = "Some text\n```yaml\nskill: test\n```\nMore text"
        blocks = extract_yaml_blocks(md)
        self.assertEqual(len(blocks), 1)
        self.assertIn("skill: test", blocks[0]["content"])

    def test_multiple_blocks(self):
        md = "```yaml\na: 1\n```\n\n```yml\nb: 2\n```"
        blocks = extract_yaml_blocks(md)
        self.assertEqual(len(blocks), 2)

    def test_no_blocks(self):
        blocks = extract_yaml_blocks("No yaml here")
        self.assertEqual(len(blocks), 0)


if __name__ == "__main__":
    unittest.main()
