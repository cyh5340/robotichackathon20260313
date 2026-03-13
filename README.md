# MedGuard

Medication Safety for Home Caregivers.

This repository currently contains robotic/vision prototypes and MedGuard system design documentation for a multi-client platform (Web + Apple app + SO101 integration).

## Documentation Index

- Product and scope overview: `docs/overview.md`
- Platform and client architecture: `docs/architecture.md`
- SO101 integration + operating guide: `docs/so101-instructions.md`
- Safety, compliance, and escalation policy: `docs/safety-and-compliance.md`
- Entity model + API endpoints: `docs/api-spec.md`

## Current Prototype Modules

- `main.py`: Voice-driven SO101 pick-and-place orchestration
- `pick_and_place.py`: Fragility-aware pick-and-place pipeline demo
- `vision.py`: Featherless VLM-based object localization
- `arm_control.py`: SO101 control, coordinate mapping, IK helpers
- `listener.py`: Smallest.ai STT/TTS interface

## Quick Start (Prototype)

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Set environment variables:

```bash
export SMALLEST_API_KEY="your_smallest_api_key"
export FEATHERLESS_API_KEY="your_featherless_api_key"
export TOOLHOUSE_API_KEY="your_toolhouse_api_key"
export ANTHROPIC_API_KEY="your_anthropic_api_key"
```

3. Run voice orchestration:

```bash
python main.py
```

## Product Direction

MedGuard is designed around four core requirements:

1. Elder profile with diseases and doctor medication notes
2. Time-based reminders and escalations
3. Adherence logging (taken/missed/skipped/held)
4. Notifications to caregivers (family, nurse, care team)

The system adds an assistive robotics layer where SO101 executes validated placement plans and routes unsafe items to a HOLD zone.
