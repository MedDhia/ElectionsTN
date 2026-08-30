"""Train the offline digit classifier for PV cells.

The training set is small (~1.3k cells from the hand-verified pilot forms) and
badly skewed — well over half the cells are zeros, because most fields are
zero-padded to four columns. Two things make a convolutional net workable
anyway: heavy affine and stroke-thickness augmentation, which is legitimate
here because the variation it simulates (pen width, slant, how the digit sits
in its cell) is exactly the variation the corpus has; and class-balanced
sampling, so the net cannot reach a good loss by predicting zero.

Evaluation is grouped by source form, never by cell. Digits from one form share
a writer and a scan, so a random split would leak the writer across the fold and
report an accuracy the pipeline will not see on an unseen form.

Usage:
  python3 tools/digit_model.py cv      # grouped cross-validation
  python3 tools/digit_model.py fit     # fit on everything -> .cache/digit_cnn.pt
"""
import os, sys
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

TRAIN = ".cache/digit_train.npz"
CERTIFIED = ".cache/digit_certified.npz"
OUT = ".cache/digit_cnn.pt"
HOLDOUT = ".cache/digit_cnn_holdout.pt"
EPOCHS = 35
BATCH = 128
torch.set_num_threads(max(1, os.cpu_count() or 1))


class Net(nn.Module):
    def __init__(self):
        super().__init__()
        self.c1, self.b1 = nn.Conv2d(1, 32, 3, padding=1), nn.BatchNorm2d(32)
        self.c2, self.b2 = nn.Conv2d(32, 32, 3, padding=1), nn.BatchNorm2d(32)
        self.c3, self.b3 = nn.Conv2d(32, 64, 3, padding=1), nn.BatchNorm2d(64)
        self.c4, self.b4 = nn.Conv2d(64, 64, 3, padding=1), nn.BatchNorm2d(64)
        self.drop = nn.Dropout(0.3)
        self.f1, self.f2 = nn.Linear(64 * 7 * 7, 128), nn.Linear(128, 10)

    def forward(self, x):
        x = F.relu(self.b1(self.c1(x)))
        x = F.max_pool2d(F.relu(self.b2(self.c2(x))), 2)
        x = F.relu(self.b3(self.c3(x)))
        x = F.max_pool2d(F.relu(self.b4(self.c4(x))), 2)
        x = self.drop(x.flatten(1))
        return self.f2(F.relu(self.f1(x)))


def augment(batch):
    """Random affine plus stroke-thickness jitter, on GPU-free tensors."""
    n = batch.shape[0]
    ang = torch.empty(n).uniform_(-12, 12) * np.pi / 180
    scale = torch.empty(n).uniform_(0.85, 1.15)
    shear = torch.empty(n).uniform_(-0.18, 0.18)
    tx = torch.empty(n).uniform_(-0.14, 0.14)
    ty = torch.empty(n).uniform_(-0.14, 0.14)
    cos, sin = torch.cos(ang) / scale, torch.sin(ang) / scale
    theta = torch.zeros(n, 2, 3)
    theta[:, 0, 0], theta[:, 0, 1], theta[:, 0, 2] = cos, -sin + shear, tx
    theta[:, 1, 0], theta[:, 1, 1], theta[:, 1, 2] = sin, cos, ty
    grid = F.affine_grid(theta, batch.shape, align_corners=False)
    out = F.grid_sample(batch, grid, align_corners=False, padding_mode="zeros")
    # Thickness: max-pool thickens a stroke, -max-pool of the negative thins it.
    thick = torch.rand(n)
    fat, thin = F.max_pool2d(out, 3, 1, 1), -F.max_pool2d(-out, 3, 1, 1)
    out = torch.where((thick < 0.2).view(-1, 1, 1, 1), fat,
                      torch.where((thick > 0.8).view(-1, 1, 1, 1), thin, out))
    return out + torch.randn_like(out) * 0.05


MAX_STEPS = 250    # per epoch; the certified set is large enough that seeing
                   # every cell each epoch buys nothing but wall clock


def train(X, y, epochs=EPOCHS, seed=0, log=False):
    torch.manual_seed(seed)
    Xt = torch.from_numpy(X).float().div(255).unsqueeze(1)
    yt = torch.from_numpy(y.astype(np.int64))
    # Class-balanced sampling: draw each class equally often per epoch.
    counts = np.bincount(y, minlength=10).astype(float)
    w = torch.from_numpy((1.0 / np.maximum(counts, 1))[y]).double()
    net = Net()
    opt = torch.optim.AdamW(net.parameters(), lr=2e-3, weight_decay=1e-4)
    steps = min(MAX_STEPS, max(1, len(yt) // BATCH))
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, 2e-3, epochs * steps)
    net.train()
    for ep in range(epochs):
        idx = torch.multinomial(w, steps * BATCH, replacement=True)
        tot = 0.0
        for s in range(steps):
            b = idx[s * BATCH:(s + 1) * BATCH]
            xb = augment(Xt[b])
            loss = F.cross_entropy(net(xb), yt[b], label_smoothing=0.05)
            opt.zero_grad(); loss.backward(); opt.step(); sched.step()
            tot += loss.item()
        if log and (ep + 1) % 20 == 0:
            print(f"    epoch {ep+1:3d}  loss {tot/steps:.4f}", flush=True)
    net.eval()
    return net


@torch.no_grad()
def predict_proba(net, X):
    Xt = torch.from_numpy(np.asarray(X)).float().div(255).unsqueeze(1)
    out = []
    for i in range(0, len(Xt), 512):
        out.append(F.softmax(net(Xt[i:i + 512]), dim=1))
    return torch.cat(out).numpy()


def load():
    d = np.load(TRAIN, allow_pickle=True)
    return d["X"], d["y"].astype(np.int64), d["code"], d["field"]


def holdout_net():
    """The net from `cv`, which never saw a pilot form. For honest evaluation."""
    net = Net()
    net.load_state_dict(torch.load(HOLDOUT, map_location="cpu"))
    net.eval()
    return net


def load_certified():
    """Cells labelled by the form's own arithmetic (tools/certify_cells.py)."""
    if not os.path.exists(CERTIFIED):
        return np.empty((0, 28, 28), np.uint8), np.empty(0, np.int64), np.empty(0, str)
    d = np.load(CERTIFIED, allow_pickle=True)
    return d["X"], d["y"].astype(np.int64), d["code"]


def cv():
    """Accuracy on the hand-verified cells, from a net that saw no human label.

    Training uses only self-certified cells, and only from forms outside the
    pilot, so every one of the 1,490 verified cells is a genuine holdout and no
    form's handwriting appears on both sides of the split. This understates the
    shipped model slightly — that one also gets the verified labels — which is
    the right direction for a number used to decide whether to trust the output.
    """
    X, y, code, _ = load()
    Xc, yc, cc = load_certified()
    keep = ~np.isin(cc, np.unique(code))
    print(f"train: {int(keep.sum())} self-certified cells from "
          f"{len(np.unique(cc[keep]))} forms", flush=True)
    print(f"test:  {len(y)} verified cells from {len(np.unique(code))} forms",
          flush=True)
    net = train(Xc[keep], yc[keep], seed=0, log=True)
    torch.save(net.state_dict(), HOLDOUT)
    p = predict_proba(net, X).argmax(1)
    ok = p == y
    print(f"\nper-digit accuracy on verified cells: {ok.mean():.4f} "
          f"({int(ok.sum())}/{len(ok)})")
    for c in range(10):
        m = y == c
        if m.any():
            print(f"  {c}: {ok[m].mean():.3f}  (n={int(m.sum())})")


def fit():
    X, y, _, _ = load()
    Xc, yc, _ = load_certified()
    X, y = np.concatenate([X, Xc]), np.concatenate([y, yc])
    print(f"training on {len(y)} cells", flush=True)
    net = train(X, y, seed=0, log=True)
    torch.save(net.state_dict(), OUT)
    print(f"trained on {len(y)} digits -> {OUT}")


if __name__ == "__main__":
    (cv if len(sys.argv) > 1 and sys.argv[1] == "cv" else fit)()
