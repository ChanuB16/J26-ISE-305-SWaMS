COMPONENT 1 - AI WASTE CLASSIFICATION

notebooks/Waste_Classification_Colab.ipynb   Trained on Colab (T4 GPU); keeps the results/outputs
models/                                      Saved models from Colab (best_model.keras = EfficientNetB0)
data/                                        trashnet.zip + raw photos (raw/local = Sri Lankan photos)
backend/guidance.json                        Disposal tips in English / Sinhala / Tamil (used by the main app)

HOW TO USE THE CLASSIFIER (NEW)
--------------------------------
Component 1 no longer runs as a separate server. It is now built into the main app
(../smartwaste_app). Start the main app:

    cd ..\smartwaste_app
    python app.py

Open http://localhost:5000 , log in as a citizen (any name), and open the Scan tab.
Pick a photo, choose a language, and tap Classify.

When the AI is 70%+ sure the photo is saved to Firebase under classifications/<id>
and the citizen gets +10 green points automatically (handled by e1_rewards.py in
../waste_forecast_routes). Officers see the photo on the Community page.

The settings for the model and the "sure" threshold live in ../smartwaste_app/settings.py:
    WASTE_CLASSIFIER_DIR = "../waste_classifier"
    CLASSIFIER_MODEL     = "best_model.keras"   # or "" to disable the Scan tab
    CLASSIFIER_SURE_LEVEL = 0.60

The main app needs these extra Python packages (added to its requirements.txt):
    pip install tensorflow "keras>=3.12" "numpy<2.1" pillow
