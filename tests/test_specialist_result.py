import json
from pathlib import Path

from geoguesser.specialist_result import normalize_specialist_result


def test_specialist_result_is_normalized_and_written(tmp_path) -> None:
    normalized, document = normalize_specialist_result(
        "rural-specialist",
        '{"candidates":["Brazil"],"evidence":["soil"],"contradictions":[],"confidence":80}',
        artifact_dir=tmp_path,
    )

    assert document["schema_version"] == "specialist-result-v1"
    assert normalized.content == json.dumps(document, ensure_ascii=False)
    assert json.loads(Path(document["artifact"]).read_text()) == document
