"""Parser for Flux2 workflows using SamplerCustomAdvanced."""

from .registry import register_parser, MetadataResult


def _find_nodes_by_type(nodes: dict, class_type: str) -> list[tuple[str, dict]]:
    return [
        (nid, node)
        for nid, node in nodes.items()
        if node.get("class_type") == class_type
    ]


def _find_input_value(nodes: dict, class_type: str, field: str):
    """Find a value from the first node of given type."""
    matches = _find_nodes_by_type(nodes, class_type)
    if matches:
        return matches[0][1].get("inputs", {}).get(field)
    return None


@register_parser(name="flux2", priority=20)
class Flux2Parser:

    @staticmethod
    def can_parse(nodes: dict) -> bool:
        """Detect Flux2 workflows by SamplerCustomAdvanced or CLIPLoader with type=flux2."""
        for node in nodes.values():
            ct = node.get("class_type", "")
            if ct == "SamplerCustomAdvanced":
                return True
            if ct == "CLIPLoader" and node.get("inputs", {}).get("type") == "flux2":
                return True
        return False

    @staticmethod
    def parse(nodes: dict, width: int, height: int) -> MetadataResult | None:
        result = MetadataResult(width=width, height=height, architecture="Flux2")

        # Prompt from CLIPTextEncode
        clip_encodes = _find_nodes_by_type(nodes, "CLIPTextEncode")
        if clip_encodes:
            for _, node in clip_encodes:
                text = node.get("inputs", {}).get("text")
                if isinstance(text, str) and text.strip():
                    result.positive_prompt = text
                    break

        # Flux2 doesn't use negative prompts
        result.negative_prompt = None

        # Model from UNETLoader
        unet_name = _find_input_value(nodes, "UNETLoader", "unet_name")
        if unet_name:
            result.model = unet_name
        else:
            # Try DualCLIPLoader or CheckpointLoaderSimple as fallback
            ckpt_name = _find_input_value(nodes, "CheckpointLoaderSimple", "ckpt_name")
            if ckpt_name:
                result.model = ckpt_name

        # Sampler from KSamplerSelect
        result.sampler = _find_input_value(nodes, "KSamplerSelect", "sampler_name")

        # Seed from RandomNoise
        seed = _find_input_value(nodes, "RandomNoise", "noise_seed")
        if seed is not None:
            result.seed = int(seed)

        # Guidance from FluxGuidance
        guidance = _find_input_value(nodes, "FluxGuidance", "guidance")
        if guidance is not None:
            result.guidance = float(guidance)

        # Steps from BasicScheduler or Flux2Scheduler
        for sched_type in ("Flux2Scheduler", "BasicScheduler"):
            steps = _find_input_value(nodes, sched_type, "steps")
            if steps is not None:
                result.steps = int(steps)
                break

        # Scheduler name
        for sched_type in ("Flux2Scheduler", "BasicScheduler"):
            sched = _find_input_value(nodes, sched_type, "scheduler")
            if sched is not None:
                result.scheduler = sched
                break

        # CLIP info
        clip_name = _find_input_value(nodes, "CLIPLoader", "clip_name")
        if clip_name:
            result.extra["clip_model"] = clip_name

        return result
