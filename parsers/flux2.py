"""Parser for SamplerCustomAdvanced workflows (Flux1, Flux2, ZImage, etc.)."""

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


def _detect_architecture(nodes: dict, model_name: str) -> str:
    """Detect architecture from CLIP loader type and model name."""
    # Check CLIPLoader type field
    for node in nodes.values():
        ct = node.get("class_type", "")
        if ct in ("CLIPLoader", "DualCLIPLoader"):
            clip_type = node.get("inputs", {}).get("type", "")
            if clip_type == "flux2":
                return "Flux2"
            if clip_type == "flux":
                return "Flux1"

    # Fallback: infer from model name
    lower = model_name.lower()
    if "flux2" in lower or "flux-2" in lower:
        return "Flux2"
    if "flux1" in lower or "flux-1" in lower or "flux-dev" in lower or "flux-schnell" in lower:
        return "Flux1"
    if "z-image" in lower or "zimage" in lower:
        return "ZImage"

    return "Unknown"


@register_parser(name="flux2", priority=20)
class AdvancedSamplerParser:

    @staticmethod
    def can_parse(nodes: dict) -> bool:
        """Detect SamplerCustomAdvanced-based workflows."""
        for node in nodes.values():
            if node.get("class_type") == "SamplerCustomAdvanced":
                return True
        return False

    @staticmethod
    def parse(nodes: dict, width: int, height: int) -> MetadataResult | None:
        # Model from UNETLoader
        model_name = _find_input_value(nodes, "UNETLoader", "unet_name") or ""

        # Detect architecture
        architecture = _detect_architecture(nodes, model_name)

        result = MetadataResult(width=width, height=height, architecture=architecture)

        if model_name:
            result.model = model_name

        # Prompt from CLIPTextEncode
        clip_encodes = _find_nodes_by_type(nodes, "CLIPTextEncode")
        if clip_encodes:
            for _, node in clip_encodes:
                text = node.get("inputs", {}).get("text")
                if isinstance(text, str) and text.strip():
                    result.positive_prompt = text
                    break

        # These workflows don't use negative prompts
        result.negative_prompt = None

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

        # Steps from schedulers
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

        # Denoise (from BasicScheduler, relevant for img2img)
        denoise = _find_input_value(nodes, "BasicScheduler", "denoise")
        if denoise is not None and float(denoise) < 1.0:
            result.denoise = float(denoise)

        # CLIP info
        for loader_type in ("CLIPLoader", "DualCLIPLoader"):
            matches = _find_nodes_by_type(nodes, loader_type)
            if matches:
                inputs = matches[0][1].get("inputs", {})
                clip_name = inputs.get("clip_name") or inputs.get("clip_name1")
                if clip_name:
                    result.extra["clip_model"] = clip_name
                break

        return result
