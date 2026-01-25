import joblib

with open("results/example/wham_output.pkl", "rb") as f:
    obj = joblib.load(f)
    print(obj[0].keys())
    