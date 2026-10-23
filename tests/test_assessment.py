import copy
import io
import json
import unittest
from unittest.mock import patch

from assessment import AssessmentError, assess_submission, validate_assessment


class AssessmentTests(unittest.TestCase):
    def setUp(self):
        self.rubric = [{"criterion": "Delivery", "max_points": 20}]
        self.result = {
            "scores": [{"criterion": "Delivery", "score": 12, "feedback": "Add evidence."}],
            "feedback": "Useful first project.",
            "points": 9999,
        }

    def test_points_derived_from_rubric_not_model_total(self):
        self.assertEqual(validate_assessment(self.result, self.rubric)["points"], 12)

    def test_integer_valued_float_normalized_for_database(self):
        self.result["scores"][0]["score"] = 12.0
        result = validate_assessment(self.result, self.rubric)
        self.assertIs(type(result["scores"][0]["score"]), int)
        self.assertEqual(result["points"], 12)
        self.assertIs(type(self.result["scores"][0]["score"]), float)

    def test_reject_invalid_scores(self):
        for score in [-1, 21, True, 1.5, float("nan"), float("inf"), "10", None]:
            with self.subTest(score=score), self.assertRaises(AssessmentError):
                result = copy.deepcopy(self.result)
                result["scores"][0]["score"] = score
                validate_assessment(result, self.rubric)

    def test_reject_unknown_missing_and_duplicate_criteria(self):
        for scores in [[], self.result["scores"] * 2,
                       [{"criterion": "Invented", "score": 1, "feedback": "No."}]]:
            with self.subTest(scores=scores), self.assertRaises(AssessmentError):
                validate_assessment({**self.result, "scores": scores}, self.rubric)

    def test_reject_absent_feedback(self):
        with self.assertRaises(AssessmentError):
            validate_assessment({**self.result, "feedback": ""}, self.rubric)

    @patch.dict("os.environ", {}, clear=True)
    def test_unconfigured_ai_never_silently_awards_points(self):
        with self.assertRaises(AssessmentError):
            assess_submission({"brief": "Brief", "rubric": self.rubric}, "Evidence", "")

    @patch("assessment.urllib.request.urlopen")
    def test_assessor_only_calls_fixed_ai_endpoint(self, open_url):
        response = {"choices": [{"message": {"content": json.dumps(self.result)}}]}
        open_url.return_value.__enter__.return_value = io.StringIO(json.dumps(response))
        result = assess_submission({"brief": "Build it", "rubric": self.rubric}, "Evidence",
                                   "https://untrusted.invalid/file", api_key="test")
        self.assertEqual(result["points"], 12)
        self.assertEqual(open_url.call_count, 1)
        request = open_url.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.openai.com/v1/chat/completions")
        self.assertEqual(request.get_header("Authorization"), "Bearer " + "test")

    @patch("assessment.urllib.request.urlopen")
    def test_malformed_ai_response_awards_nothing(self, open_url):
        open_url.return_value.__enter__.return_value = io.StringIO('{"choices": []}')
        with self.assertRaises(AssessmentError):
            assess_submission({"brief": "Build it", "rubric": self.rubric}, "Evidence", "",
                              api_key="test")


if __name__ == "__main__":
    unittest.main()
