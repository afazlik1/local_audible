"""Compatibility for the pinned S2 Pro MLX checkpoint's unprefixed keys.

The installed mlx-audio sanitizer accepts model.* keys and original PyTorch
keys, but this converted checkpoint stores the inner model's keys directly.
Keep strict weight/shape validation; never bypass missing parameter errors.
"""
FISH_REVISION = "4e9863f2915d6df6dcde5b6d7e1a351bddbc5986"
INNER_ROOTS = {"embeddings", "layers", "norm", "output", "fast_embeddings",
               "fast_layers", "fast_norm", "fast_output", "codebook_embeddings"}


def normalize_weights(weights):
    return {f"model.{key}" if key.split(".", 1)[0] in INNER_ROOTS else key: value
            for key, value in weights.items()}


def include_codec_aliases(weights, expected_keys):
    """Mirror CausalWNConv's derived inner parameters, not random defaults.

    Its constructor aliases conv.conv.weight to weight_v and conv.conv.bias
    to bias; forward replaces the inner weight with the normalized weight.
    The checkpoint stores only the authoritative outer parameters.
    """
    result = dict(weights)
    for key in expected_keys:
        for suffix, source_suffix in [(".conv.conv.weight", ".weight_v"), (".conv.conv.bias", ".bias")]:
            if key.endswith(suffix) and key not in result:
                source = key[:-len(suffix)] + source_suffix
                if source in weights:
                    result[key] = weights[source]
    return result


def load_fish_model(repo):
    import json
    from pathlib import Path
    import mlx.core as mx
    from mlx.utils import tree_flatten
    from unittest.mock import patch
    from mlx_audio.codec.models.fish_s1_dac.fish_s1_dac import DAC, build_ae
    from mlx_audio.tts.models.fish_qwen3_omni.fish_speech import Model
    from mlx_audio.tts.utils import load_model
    original = Model.sanitize
    def sanitize(self, weights):
        return original(self, normalize_weights(weights))
    def load_codec(model_path):
        path = Path(model_path) / "codec-mlx"
        config = json.loads((path / "config.json").read_text())
        codec = build_ae(**config)
        weights = codec.sanitize(mx.load(str(path / "model.safetensors")))
        weights = include_codec_aliases(weights, dict(tree_flatten(codec.parameters())))
        codec.load_weights(list(weights.items()), strict=True)
        mx.eval(codec.parameters())
        codec.eval()
        return codec
    # Runs only in the disposable inference worker; no package/cache edits.
    with patch.object(Model, "sanitize", sanitize), patch.object(DAC, "from_pretrained", side_effect=load_codec):
        return load_model(repo, revision=FISH_REVISION, strict=True)
