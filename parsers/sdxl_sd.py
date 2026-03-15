"""Parser for KSampler-based workflows (SDXL, SD1.5, Pony, etc.)."""

from .registry import register_parser, MetadataResult


def _find_nodes_by_type(nodes: dict, class_type: str) -> list[tuple[str, dict]]:
    """Find all nodes matching a class_type."""
    return [
        (nid, node)
        for nid, node in nodes.items()
        if node.get("class_type") == class_type
    ]


def _trace_input(nodes: dict, node_id: str, input_name: str) -> tuple[str, dict] | None:
    """Trace an input connection to its source node."""
    node = nodes.get(node_id)
    if not node:
        return None
    inp = node.get("inputs", {}).get(input_name)
    if isinstance(inp, list) and len(inp) >= 1:
        source_id = str(inp[0])
        source_node = nodes.get(source_id)
        if source_node:
            return (source_id, source_node)
    return None


def _get_prompt_text(nodes: dict, node_id: str, input_name: str) -> str | None:
    """Trace a KSampler positive/negative input to get the prompt text."""
    source = _trace_input(nodes, node_id, input_name)
    if not source:
        return None
    _, source_node = source
    ct = source_node.get("class_type", "")
    inputs = source_node.get("inputs", {})
    if "CLIPTextEncode" in ct:
        text = inputs.get("text")
        return text if isinstance(text, str) else None
    return None


def _infer_architecture(nodes: dict, model_name: str) -> str:
    """Infer architecture from CLIPLoader type, then model filename."""
    # Check CLIPLoader type field first
    for node in nodes.values():
        ct = node.get("class_type", "")
        if ct in ("CLIPLoader", "DualCLIPLoader"):
            clip_type = node.get("inputs", {}).get("type", "")
            if clip_type == "qwen_image":
                # Could be Pony v7 or similar next-gen model
                lower = model_name.lower()
                if "pony" in lower:
                    return "Pony"
                return "SDXL (Next-gen)"

    lower = model_name.lower()
    if "pony" in lower:
        return "Pony"
    if "sdxl" in lower or "sd_xl" in lower:
        return "SDXL"
    if "sd3" in lower:
        return "SD3"
    if "sd1" in lower or "v1-5" in lower or "v1_5" in lower:
        return "SD 1.5"
    return "SD / SDXL"


@register_parser(name="sdxl_sd", priority=10)
class SDXLParser:

    @staticmethod
    def can_parse(nodes: dict) -> bool:
        """Detect KSampler-based workflows."""
        for node in nodes.values():
            ct = node.get("class_type", "")
            if ct in ("KSampler", "KSamplerAdvanced"):
                return True
        return False

    @staticmethod
    def parse(nodes: dict, width: int, height: int) -> MetadataResult | None:
        result = MetadataResult(width=width, height=height)

        # Find KSampler
        ksamplers = _find_nodes_by_type(nodes, "KSampler")
        if not ksamplers:
            ksamplers = _find_nodes_by_type(nodes, "KSamplerAdvanced")
        if not ksamplers:
            return None

        ksampler_id, ksampler = ksamplers[0]
        inputs = ksampler.get("inputs", {})

        # Sampling params
        result.seed = inputs.get("seed") or inputs.get("noise_seed")
        result.steps = inputs.get("steps")
        result.cfg = inputs.get("cfg")
        result.sampler = inputs.get("sampler_name")
        result.scheduler = inputs.get("scheduler")
        result.denoise = inputs.get("denoise")

        # Convert numeric types
        if result.seed is not None:
            result.seed = int(result.seed)
        if result.steps is not None:
            result.steps = int(result.steps)
        if result.cfg is not None:
            result.cfg = float(result.cfg)
        if result.denoise is not None:
            result.denoise = float(result.denoise)

        # Trace prompts from KSampler connections
        result.positive_prompt = _get_prompt_text(nodes, ksampler_id, "positive")
        result.negative_prompt = _get_prompt_text(nodes, ksampler_id, "negative")

        # Mark empty negative prompt explicitly
        if result.negative_prompt is not None and result.negative_prompt.strip() == "":
            result.negative_prompt = "(empty)"

        # Find model — try CheckpointLoaderSimple first, then UNETLoader
        model_name = ""
        checkpoints = _find_nodes_by_type(nodes, "CheckpointLoaderSimple")
        if checkpoints:
            model_name = checkpoints[0][1].get("inputs", {}).get("ckpt_name", "")
        else:
            unet_loaders = _find_nodes_by_type(nodes, "UNETLoader")
            if unet_loaders:
                model_name = unet_loaders[0][1].get("inputs", {}).get("unet_name", "")

        if model_name:
            result.model = model_name
        result.architecture = _infer_architecture(nodes, model_name)

        return result
