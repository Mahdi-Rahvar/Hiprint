#!/usr/bin/env python3
"""3-shot APAC photorealistic render prompt engine.

Templates emit three prompts per SKU/component: flat-lay, pedestal isometric, signature view.
Signature view varies by category: boards (exploded isometric), printheads (10x macro nozzle),
consumables (fluid suspension).

Each prompt carries the APAC standard tail: 8K Hasselblad H6D-100c aesthetic, f/8, no motion blur,
no watermarks, no synthetic artifacts, no illegible typography.
"""

FLAT_LAY = """
Product: {subject}

Perspective: Strict 90-degree orthogonal overhead view.
Environment: Minimalist matte stone slab with subtle natural architectural texture.
Lighting: Soft directional daylight cast at 45 degrees, realistic ambient occlusion, razor-sharp edge transitions, zero artificial glare.

Fidelity: 8K photorealistic, Hasselblad H6D-100c medium format aesthetic, f/8 aperture, zero motion blur, crisp optical depth.
Cleanliness: Absolute omission of synthetic artifacts, distorted traces, hallucinated watermarks, or unreadable typography.
"""

PEDESTAL_ISOMETRIC = """
Product: {subject}

Perspective: 45-degree elevated three-quarter isometric framing.
Environment: Centered on an industrial matte-black circular presentation pedestal.
Lighting: Precision studio rim lighting and dual fill lights accentuating vertical dimension, connector banks, heatsink fins, and board topography.

Fidelity: 8K photorealistic, Hasselblad H6D-100c medium format aesthetic, f/8 aperture, zero motion blur, crisp optical depth.
Cleanliness: Absolute omission of synthetic artifacts, distorted traces, hallucinated watermarks, or unreadable typography.
"""

SIGNATURE_BOARD = """
Product: {subject}

Perspective: Precision exploded isometric perspective, decoupled microchips, heatsinks, and multi-layer PCB substrate floating along a clean central axis.
Environment: Clean white infinity background with subtle drop shadow beneath each floating element.
Lighting: Studio rim lighting emphasizing each discrete component's 3D form.

Fidelity: 8K photorealistic, Hasselblad H6D-100c medium format aesthetic, f/8 aperture, zero motion blur, crisp optical depth.
Cleanliness: Absolute omission of synthetic artifacts, distorted traces, hallucinated watermarks, or unreadable typography.
"""

SIGNATURE_PRINTHEAD = """
Product: {subject}

Perspective: Ultra-macro 10x close-up focusing directly on the mirror-finish nozzle plate and micro-orifices.
Environment: Controlled studio background with metallic refraction highlights.
Lighting: Controlled metallic studio refraction showing individual nozzle detail.

Fidelity: 8K photorealistic, Hasselblad H6D-100c medium format aesthetic, f/8 aperture, zero motion blur, crisp optical depth.
Cleanliness: Absolute omission of synthetic artifacts, distorted traces, hallucinated watermarks, or unreadable typography.
"""

SIGNATURE_CONSUMABLE = """
Product: {subject}

Perspective: Dynamic high-speed commercial fluid suspension, showcasing high-density CMYK pigmentation, fluid droplet viscosity, and translucent bottle refraction.
Environment: Studio background with refraction highlights on the fluid suspension.
Lighting: Studio lighting emphasizing pigment density and translucency.

Fidelity: 8K photorealistic, Hasselblad H6D-100c medium format aesthetic, f/8 aperture, zero motion blur, crisp optical depth.
Cleanliness: Absolute omission of synthetic artifacts, distorted traces, hallucinated watermarks, or unreadable typography.
"""


def build_prompts(component):
    """Build three render prompts for a component.

    Args:
        component: dict with 'canonical_name', 'category', 'visual'

    Returns:
        dict with keys 'shot_1', 'shot_2', 'shot_3'
    """
    subject = f"{component['canonical_name']} — {component['visual']}"

    shot_1 = FLAT_LAY.format(subject=subject)
    shot_2 = PEDESTAL_ISOMETRIC.format(subject=subject)

    if component['category'] == 'board':
        shot_3 = SIGNATURE_BOARD.format(subject=subject)
    elif component['category'] == 'printhead':
        shot_3 = SIGNATURE_PRINTHEAD.format(subject=subject)
    elif component['category'] == 'consumable':
        shot_3 = SIGNATURE_CONSUMABLE.format(subject=subject)
    else:
        shot_3 = SIGNATURE_BOARD.format(subject=subject)

    return {'shot_1': shot_1, 'shot_2': shot_2, 'shot_3': shot_3}


if __name__ == "__main__":
    # Test: Hoson mainboard
    test = {
        'canonical_name': 'Hoson Mainboard (Generic)',
        'category': 'board',
        'visual': 'Multi-layer PCB with heatsink-mounted MOSFETs, optocoupler array, DIN connectors'
    }
    prompts = build_prompts(test)
    print("SHOT 1 (Flat-Lay):")
    print(prompts['shot_1'][:200] + "...")
    print("\nSHOT 2 (Pedestal Isometric):")
    print(prompts['shot_2'][:200] + "...")
    print("\nSHOT 3 (Board Exploded):")
    print(prompts['shot_3'][:200] + "...")
