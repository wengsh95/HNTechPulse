from src.utils.text import normalize_cjk_mixed_spacing


def test_normalize_cjk_mixed_spacing_tightens_cn_ascii_edges():
    assert normalize_cjk_mixed_spacing("Meta 自家 AI 聊天机器人") == "Meta自家AI聊天机器人"
    assert normalize_cjk_mixed_spacing("Nvidia 要给 Windows PC 造 CPU") == "Nvidia要给Windows PC造CPU"


def test_normalize_cjk_mixed_spacing_keeps_ascii_phrase_spaces():
    assert normalize_cjk_mixed_spacing("Windows PC and OpenAI API") == "Windows PC and OpenAI API"

