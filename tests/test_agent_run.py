from scripts.agent_run import DOWNSTREAM_FROM, _stale_recovery_steps


def test_write_script_downstream_steps_match_publish_pipeline_order():
    assert DOWNSTREAM_FROM["write_script"] == [
        "write_script",
        "translate_comments",
        "synthesize_audio",
        "title",
        "cover_image",
        "cover_thumbnail",
        "publish_guide",
        "prepare_render",
        "render",
    ]


def test_stale_content_recovery_uses_publish_pipeline_order():
    steps = _stale_recovery_steps(
        {
            "stale_artifacts": [
                {
                    "artifact": "data/2026-06-09/script.json",
                    "reason": "content.json is newer than script.json",
                }
            ]
        }
    )

    assert steps == DOWNSTREAM_FROM["write_script"]
