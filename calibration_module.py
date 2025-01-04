# -*- coding: utf-8 -*-
"""Calibration_Module.ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1wmmV6Edc7hEP7kgVRbp8aPTkEt-oIlZC
"""

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, TensorDataset
import matplotlib.pyplot as plt
import pandas as pd
from sklearn.model_selection import train_test_split
import torch
import torch.nn.functional as F
from sklearn.calibration import calibration_curve
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
import matplotlib.pyplot as plt
import numpy as np
from scipy.ndimage import gaussian_filter1d
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
import numpy as np

!pip install gdown
!gdown 'https://drive.google.com/uc?id=1A0xoL44Yg68ixd-FuIJn2VC4vdZ6M2gn'
!unzip -q WildRF.zip
def get_req_set(path):
  df = pd.read_csv(path)
  features_df = df['features'].str.strip('[]').str.split(',', expand=True)
  features_df = features_df.astype(float)
  features_df.columns = [f'feature_{i}' for i in range(features_df.shape[1])]
  df_expanded = pd.concat([features_df, df['label']], axis=1)
  X = df_expanded.drop(columns=['label'])
  y = df_expanded['label']
  X_tensor = torch.tensor(X.values, dtype=torch.float32)
  y_tensor = torch.tensor(y.values, dtype=torch.long)
  dataset = TensorDataset(X_tensor, y_tensor)
  print(len(dataset))
  temp_loader = DataLoader(dataset, batch_size=32, shuffle=True)
  return temp_loader
train_loader = get_req_set('/content/train_features.csv')
val_loader_1 = get_req_set('/content/facebook_features.csv')
val_loader_2 = get_req_set('/content/reddit_features.csv')
val_loader_3 = get_req_set('/content/twitter_features.csv')
val_loader_4 = get_req_set('/content/val_features.csv')

class DNN(nn.Module):
    def __init__(self, input_dim, hidden_dim_1, hidden_dim_2, output_dim, dropout_prob=0.2):
        super(DNN, self).__init__()
        self.fc1 = nn.Linear(input_dim, hidden_dim_1)
        self.relu = nn.ReLU()
        self.dropout1 = nn.Dropout(p=dropout_prob)
        self.fc2 = nn.Linear(hidden_dim_1, hidden_dim_2)
        self.dropout2 = nn.Dropout(p=dropout_prob)
        self.fc3 = nn.Linear(hidden_dim_2, output_dim)

    def forward(self, x):
        x = self.fc1(x)
        x = self.relu(x)
        x = self.dropout1(x)
        x = self.fc2(x)
        x = self.relu(x)
        x = self.dropout2(x)
        x = self.fc3(x)
        return x

# Updated loop with four validation datasets and additional metrics
input_dim = 768      # Number of features in the produced dataset
hidden_dim_1 = 128
hidden_dim_2 = 256
output_dim = 2 # Number of classes -- 2
model = DNN(input_dim, hidden_dim_1, hidden_dim_2, output_dim)

"""CALIBRATING on TRAIN SET - WILDRF"""

# CALIBRATION FOR VALIDATION DS -- WILDRF

model = DNN(input_dim, hidden_dim_1, hidden_dim_2, output_dim)  # Replace with your model class
model.load_state_dict(torch.load('/content/model_weights_Final_Model_WildRF.pth'))  # Load saved weights
model.eval()  # Set the model to evaluation mode

softmax_probs = []
true_labels = []
with torch.no_grad():
    for inputs, labels in train_loader: #train
        logits = model(inputs)
        probs = F.softmax(logits, dim=1)
        softmax_probs.append(probs.cpu().numpy())
        true_labels.append(labels.cpu().numpy())
softmax_probs = np.concatenate(softmax_probs, axis=0)
true_labels = np.concatenate(true_labels, axis=0)

def plot_calibration_curve(y_true, y_prob, n_bins=100, label='Uncalibrated'):
    prob_true, prob_pred = calibration_curve(y_true, y_prob, n_bins=n_bins, strategy='uniform')
    plt.plot(prob_pred, prob_true, marker='o', label=label)
    return prob_true, prob_pred

positive_probs = softmax_probs[:, 1]
positive_labels = true_labels
plt.figure(figsize=(8, 6))
plot_calibration_curve(positive_labels, positive_probs, label='Uncalibrated')
plt.plot([0, 1], [0, 1], 'k--', label='Perfect Calibration')
plt.xlabel('Mean Predicted Probability')
plt.ylabel('Fraction of Positives')
plt.title('Calibration Curve')
plt.legend()
plt.show()

# Assuming `softmax_probs` are already probabilities in [0, 1] (logits transformed by softmax)
positive_class_idx = 1  # Define the positive class index
positive_probs = softmax_probs[:, positive_class_idx]  # Extract positive class probabilities
positive_labels = true_labels # Binary labels for the positive class

# Fit PLATT SCALING -- scaled Logistic Regression to logits
log_reg = LogisticRegression()
log_reg.fit(positive_probs.reshape(-1,1), true_labels)  # Fit on positive class probabilities and binary labels

# Predict calibrated probabilities for the positive class
calibrated_probs_iso = log_reg.predict_proba(positive_probs.reshape(-1,1))[:,1]

plt.figure(figsize=(8, 6))

# Uncalibrated
plot_calibration_curve(true_labels, positive_probs, label='Uncalibrated')

# Calibrated
plot_calibration_curve(true_labels, calibrated_probs_iso, label='Platt Scaling')

# Perfect calibration line
plt.plot([0, 1], [0, 1], 'k--', label='Perfect Calibration')

# Plot settings
plt.xlabel('Mean Predicted Probability')
plt.ylabel('Fraction of Positives')
plt.title('Calibration Curve - Training')
plt.legend()
plt.show()

def compute_ece(y_true, y_prob, n_bins=100):
    bins = np.linspace(0, 1, n_bins + 1)  # Define bin edges
    bin_indices = np.digitize(y_prob, bins) - 1  # Assign probabilities to bins

    ece = 0.0
    for i in range(n_bins):
        bin_mask = bin_indices == i
        bin_count = np.sum(bin_mask)
        if bin_count > 0:
            bin_confidence = np.mean(y_prob[bin_mask])  # Mean predicted probability
            bin_accuracy = np.mean(y_true[bin_mask])  # Fraction of positives
            ece += (bin_count / len(y_prob)) * np.abs(bin_accuracy - bin_confidence)

    return ece

# Compute ECE for uncalibrated and calibrated models
ece_uncalibrated = compute_ece(true_labels, positive_probs)
ece_calibrated = compute_ece(true_labels, calibrated_probs_iso)

print(f"ECE (Uncalibrated) on Val: {ece_uncalibrated:.4f}")
print(f"ECE (Calibrated): on Val {ece_calibrated:.4f}")

"""CHECKING performance of Calibrated Model on VAL Dataset -- WILDRF"""

# chceking uncalibrated model on VAL
softmax_probs = []
true_labels = []
with torch.no_grad():
    for inputs, labels in val_loader_4: #val
        logits = model(inputs)
        probs = F.softmax(logits, dim=1)
        softmax_probs.append(probs.cpu().numpy())
        true_labels.append(labels.cpu().numpy())
softmax_probs = np.concatenate(softmax_probs, axis=0)
true_labels = np.concatenate(true_labels, axis=0)
logits = softmax_probs

# Assuming `softmax_probs` are already probabilities in [0, 1] (logits transformed by softmax)
positive_class_idx = 1  # Define the positive class index
positive_probs = softmax_probs[:, positive_class_idx]  # Extract positive class probabilities
positive_labels = true_labels  # Binary labels for the positive class

calibrated_probs_iso = log_reg.predict_proba(positive_probs.reshape(-1,1))[:,1]

# Plot Calibration Curve
def plot_calibration_curve(y_true, y_prob, n_bins=100, label=None):
    from sklearn.calibration import calibration_curve
    prob_true, prob_pred = calibration_curve(y_true, y_prob, n_bins=n_bins, strategy='uniform')
    plt.plot(prob_pred, prob_true, marker='o', label=label)

plt.figure(figsize=(8, 6))

# Uncalibrated
plot_calibration_curve(true_labels, positive_probs, label='Uncalibrated')

# Calibrated
plot_calibration_curve(true_labels, calibrated_probs_iso, label='Platt Scaling')

# Perfect calibration line
plt.plot([0, 1], [0, 1], 'k--', label='Perfect Calibration')

# Plot settings
plt.xlabel('Mean Predicted Probability')
plt.ylabel('Fraction of Positives')
plt.title('Calibration Curve - Validation Dataset')
plt.legend()
plt.show()

# Compute ECE for uncalibrated and calibrated models
ece_uncalibrated = compute_ece(true_labels, positive_probs)
ece_calibrated = compute_ece(true_labels, calibrated_probs_iso)

print(f"ECE (Uncalibrated) on Val: {ece_uncalibrated:.4f}")
print(f"ECE (Calibrated): on Val {ece_calibrated:.4f}")

# chceking uncalibrated model on Facebook
softmax_probs = []
true_labels = []
with torch.no_grad():
    for inputs, labels in val_loader_1: #FACEBOOK
        logits = model(inputs)
        probs = F.softmax(logits, dim=1)
        softmax_probs.append(probs.cpu().numpy())
        true_labels.append(labels.cpu().numpy())
softmax_probs = np.concatenate(softmax_probs, axis=0)
true_labels = np.concatenate(true_labels, axis=0)
logits = softmax_probs

# Assuming `softmax_probs` are already probabilities in [0, 1] (logits transformed by softmax)
positive_class_idx = 1  # Define the positive class index
positive_probs = softmax_probs[:, positive_class_idx]  # Extract positive class probabilities
positive_labels = true_labels  # Binary labels for the positive class

calibrated_probs_iso = log_reg.predict_proba(positive_probs.reshape(-1,1))[:,1]

# Plot Calibration Curve
def plot_calibration_curve(y_true, y_prob, n_bins=100, label=None):
    from sklearn.calibration import calibration_curve
    prob_true, prob_pred = calibration_curve(y_true, y_prob, n_bins=n_bins, strategy='uniform')
    plt.plot(prob_pred, prob_true, marker='o', label=label)

plt.figure(figsize=(8, 6))

# Uncalibrated
plot_calibration_curve(true_labels, positive_probs, label='Uncalibrated')

# Calibrated
plot_calibration_curve(true_labels, calibrated_probs_iso, label='Platt Scaling')

# Perfect calibration line
plt.plot([0, 1], [0, 1], 'k--', label='Perfect Calibration')

# Plot settings
plt.xlabel('Mean Predicted Probability')
plt.ylabel('Fraction of Positives')
plt.title('Calibration Curve - Facebook Validation')
plt.legend()
plt.show()

# Compute ECE for uncalibrated and calibrated models
ece_uncalibrated = compute_ece(true_labels, positive_probs)
ece_calibrated = compute_ece(true_labels, calibrated_probs_iso)

print(f"ECE (Uncalibrated) on Facebook: {ece_uncalibrated:.4f}")
print(f"ECE (Calibrated): on Facebook {ece_calibrated:.4f}")

softmax_probs = []
true_labels = []
with torch.no_grad():
    for inputs, labels in val_loader_2: #reddit
        logits = model(inputs)
        probs = F.softmax(logits, dim=1)
        softmax_probs.append(probs.cpu().numpy())
        true_labels.append(labels.cpu().numpy())
softmax_probs = np.concatenate(softmax_probs, axis=0)
true_labels = np.concatenate(true_labels, axis=0)
logits = softmax_probs
# Assuming `softmax_probs` are already probabilities in [0, 1] (logits transformed by softmax)
positive_class_idx = 1  # Define the positive class index
positive_probs = softmax_probs[:, positive_class_idx]  # Extract positive class probabilities
positive_labels = (true_labels == positive_class_idx).astype(int)  # Binary labels for the positive class

calibrated_probs_iso = log_reg.predict_proba(positive_probs.reshape(-1,1))[:,1]

# Plot Calibration Curve
def plot_calibration_curve(y_true, y_prob, n_bins=100, label=None):
    from sklearn.calibration import calibration_curve
    prob_true, prob_pred = calibration_curve(y_true, y_prob, n_bins=n_bins, strategy='uniform')
    plt.plot(prob_pred, prob_true, marker='o', label=label)

plt.figure(figsize=(8, 6))

# Uncalibrated
plot_calibration_curve(true_labels, positive_probs, label='Uncalibrated')

# Calibrated
plot_calibration_curve(true_labels, calibrated_probs_iso, label='Platt Scaling')

# Perfect calibration line
plt.plot([0, 1], [0, 1], 'k--', label='Perfect Calibration')

# Plot settings
plt.xlabel('Mean Predicted Probability')
plt.ylabel('Fraction of Positives')
plt.title('Calibration Curve - Reddit Validation')
plt.legend()
plt.show()
# Compute ECE for uncalibrated and calibrated models
ece_uncalibrated = compute_ece(true_labels, positive_probs)
ece_calibrated = compute_ece(true_labels, calibrated_probs_iso)

print(f"ECE (Uncalibrated) on Reddit: {ece_uncalibrated:.4f}")
print(f"ECE (Calibrated): on Reddit {ece_calibrated:.4f}")

# chceking uncalibrated model on twitter
softmax_probs = []
true_labels = []
with torch.no_grad():
    for inputs, labels in val_loader_3: #twitter
        logits = model(inputs)
        probs = F.softmax(logits, dim=1)
        softmax_probs.append(probs.cpu().numpy())
        true_labels.append(labels.cpu().numpy())
softmax_probs = np.concatenate(softmax_probs, axis=0)
true_labels = np.concatenate(true_labels, axis=0)
logits = softmax_probs
# Assuming `softmax_probs` are already probabilities in [0, 1] (logits transformed by softmax)
positive_class_idx = 1  # Define the positive class index
positive_probs = softmax_probs[:, positive_class_idx]  # Extract positive class probabilities
positive_labels = (true_labels == positive_class_idx).astype(int)  # Binary labels for the positive class

calibrated_probs_iso = log_reg.predict_proba(positive_probs.reshape(-1,1))[:,1]

# Plot Calibration Curve
def plot_calibration_curve(y_true, y_prob, n_bins=100, label=None):
    from sklearn.calibration import calibration_curve
    prob_true, prob_pred = calibration_curve(y_true, y_prob, n_bins=n_bins, strategy='uniform')
    plt.plot(prob_pred, prob_true, marker='o', label=label)

plt.figure(figsize=(8, 6))

# Uncalibrated
plot_calibration_curve(true_labels, positive_probs, label='Uncalibrated')

# Calibrated
plot_calibration_curve(true_labels, calibrated_probs_iso, label='Platt Scaling')

# Perfect calibration line
plt.plot([0, 1], [0, 1], 'k--', label='Perfect Calibration')

# Plot settings
plt.xlabel('Mean Predicted Probability')
plt.ylabel('Fraction of Positives')
plt.title('Calibration Curve - Twitter Validation')
plt.legend()
plt.show()
# Compute ECE for uncalibrated and calibrated models
ece_uncalibrated = compute_ece(true_labels, positive_probs)
ece_calibrated = compute_ece(true_labels, calibrated_probs_iso)

print(f"ECE (Uncalibrated) on Twitter: {ece_uncalibrated:.4f}")
print(f"ECE (Calibrated): on Twitter {ece_calibrated:.4f}")

