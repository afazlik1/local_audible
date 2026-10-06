from backend.fish_compat import normalize_weights, include_codec_aliases


def test_converted_weights_keep_quantization_and_gain_model_prefix():
    weights = {"layers.9.attention.wo.weight": 1, "layers.9.attention.wo.scales": 2,
               "layers.9.attention.wo.biases": 3, "embeddings.weight": 4,
               "codebook_embeddings.weight": 5, "fast_layers.0.attention.wqkv.weight": 6}
    assert normalize_weights(weights) == {"model." + k: v for k, v in weights.items()}
    assert weights["embeddings.weight"] == 4


def test_native_and_unknown_weight_names_are_not_reinterpreted():
    weights = {"model.layers.0.weight": 1, "text_model.model.layers.0.weight": 2,
               "audio_decoder.layers.0.weight": 3, "unknown.weight": 4}
    assert normalize_weights(weights) == weights


def test_codec_aliases_only_come_from_checkpoint_parameters():
    weights = {"decoder.block.weight_v": 1, "decoder.block.bias": 2}
    result = include_codec_aliases(weights, ["decoder.block.conv.conv.weight", "decoder.block.conv.conv.bias", "missing.conv.conv.weight"])
    assert result["decoder.block.conv.conv.weight"] == 1
    assert result["decoder.block.conv.conv.bias"] == 2
    assert "missing.conv.conv.weight" not in result
    assert len(weights) == 2
