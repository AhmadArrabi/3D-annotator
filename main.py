import argparse
from src.core import load_ct_scan
from src.vis import InteractiveAnnotator

def main():
    parser = argparse.ArgumentParser(description="3D CT Annotator")
    parser.add_argument("--path", type=str, help="Path to NIfTI file. If omitted, uses synthetic data.")
    args = parser.parse_args()
    
    print("Loading data...")
    volume = load_ct_scan(args.path)
    print(f"Volume shape: {volume.shape}")
    
    print("Starting interactive annotator...")
    annotator = InteractiveAnnotator(volume)

if __name__ == "__main__":
    main()
