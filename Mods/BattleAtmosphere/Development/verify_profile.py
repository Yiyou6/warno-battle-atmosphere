"""Compatibility entry point for the current offline validator."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
candidate=Path(__file__).resolve().parents[1]/'GameData/Gameplay/Skirmish/SkirmishMacros/SkirmishAttacks.ndf'
if 'export Attack_Armor_BA ' in candidate.read_text(encoding='utf-8-sig'):
    from validate_combined_profile import main
else:
    from validate_profile import main
if __name__ == '__main__':
    main()
