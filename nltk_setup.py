"""
NLTK Data Setup Script for Koyeb/Cloud Deployment
Downloads required NLTK data at startup
"""
import nltk
import os

def setup_nltk():
    """Download required NLTK data packages."""
    # Set a custom download directory that works on Koyeb
    nltk_data_dir = os.path.join(os.getcwd(), 'nltk_data')
    os.makedirs(nltk_data_dir, exist_ok=True)
    
    # Add the directory to NLTK's data path
    nltk.data.path.insert(0, nltk_data_dir)
    
    # Download required data
    try:
        print("Checking NLTK 'words' corpus...")
        nltk.data.find('corpora/words')
        print("NLTK 'words' corpus already available.")
    except LookupError:
        print("Downloading NLTK 'words' corpus...")
        nltk.download('words', download_dir=nltk_data_dir)
        print("NLTK 'words' corpus downloaded successfully.")
    
    return True

if __name__ == "__main__":
    setup_nltk()
