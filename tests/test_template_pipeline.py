"""Offline guardrails for the template-only creative pipeline."""
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from lib.creative_research import build_research_brief, research_inventory
from lib.ideas import novelty_issue
from s3_storyboard import templates
from tools import run_all
from webui.server import SETTINGS_SCHEMA, app


class TemplatePipelineTests(unittest.TestCase):
    def test_research_has_all_four_sources_and_rotates_topic(self):
        self.assertEqual(research_inventory()["missing"], [])
        first = build_research_brief()
        second = build_research_brief({first["hotspot"]["title"]})
        self.assertNotEqual(first["hotspot"]["title"], second["hotspot"]["title"])
        self.assertTrue(first["viral_examples"] or first["short_drama_patterns"])
        self.assertTrue(first["benchmark_patterns"])

    def test_standard_dialogue_is_rejected(self):
        self.assertIn("标准版", novelty_issue({"1": "旧台词"}, {"1": "旧台词"}))

    def test_old_mode_is_not_exposed(self):
        fields = [field["key"] for group in SETTINGS_SCHEMA["groups"]
                  for field in group["fields"]]
        self.assertNotIn("mode", fields)

    def test_dry_storyboard_does_not_call_model_or_create_job(self):
        with patch.object(run_all, "log"), patch.object(run_all, "create_job") as create_job:
            with patch.object(templates, "adapt_lines") as adapt:
                self.assertTrue(run_all.run_stage_storyboard(dry=True))
                adapt.assert_not_called()
                create_job.assert_not_called()

    def test_scan_login_buttons_use_real_postflow_commands_without_launching_in_test(self):
        client = TestClient(app)
        with patch("webui.server.subprocess.Popen") as popen:
            popen.return_value.pid = 12345
            for path, command in (("xiaohongshu", "xiaohongshu"),
                                  ("shipinhao", "tencent")):
                response = client.post(f"/api/action/{path}_login")
                self.assertEqual(response.status_code, 200)
                args = popen.call_args.args[0]
                self.assertEqual(args[1:3], [command, "login"])
                self.assertIn("--headed", args)

    def test_failed_creative_quality_never_falls_back(self):
        sample = {
            "id": "test", "name": "测试模板",
            "shots": [
                {"seq": 1, "duration": 4, "speaker": "S1", "cast_refs": [],
                 "start_state": "门口", "end_state": "门口", "narration": "这句是旧台词"},
                {"seq": 2, "duration": 4, "speaker": "S2", "cast_refs": [],
                 "start_state": "门口", "end_state": "门口", "narration": "爱优护轻便侠来了"},
            ],
        }
        research = {"hotspot": {"title": "测试热点"}}
        repeated = {"lines": {"1": "这句是旧台词", "2": "爱优护轻便侠来了"},
                    "creative_design": {key: "已写" for key in
                                        ("hook", "beat", "twist", "novelty", "reference_use")}}
        with patch.object(templates, "chat_json", return_value=repeated):
            with self.assertRaisesRegex(RuntimeError, "已停止本条视频"):
                templates.adapt_lines(sample, "测试热点", research_brief=research)


if __name__ == "__main__":
    unittest.main()
