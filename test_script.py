import numpy as np
import src.core as core
import src.vis as vis
import matplotlib.pyplot as plt

def test_pipeline():
    print("Testing synthetic generation...")
    vol = core.create_synthetic_phantom(shape=(64, 64, 64))
    assert vol.shape == (64, 64, 64)
    print("Synthetic generation OK.")
    
    print("Testing AIP generation...")
    aip_ap = core.generate_aip(vol, axis=1)
    assert aip_ap.shape == (64, 64)
    print("AIP generation OK.")
    
    # Can't easily test interactive GUI in headless, but we can instantiation
    print("Testing Annotator instantiation (headless)...")
    try:
        # Use Agg backend to avoid GUI errors
        plt.switch_backend('Agg')
        ann = vis.InteractiveAnnotator(vol)
        print("Annotator instantiated OK.")
    except Exception as e:
        print(f"Annotator instantiation failed: {e}")

if __name__ == "__main__":
    test_pipeline()
