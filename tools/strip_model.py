"""Read a whole field at once instead of four cells independently.

`digit_model` classifies each box on its own, which discards what the four boxes
of a field share — one hand, one pen, one scan — and the joint prior that counts
are zero-padded, so a leading 9 is rare where a trailing one is not. It is also
brittle in the way the unread forms are: their cells are located but misread, and
a per-cell crop three pixels out clips its digit where a strip crop three pixels
out barely moves.

This reads the strip and emits four digit distributions, which is exactly the
shape `pv_decode.FieldProbs` consumes — so it drops in beside the cell classifier
rather than replacing the machinery around it. The decoder, the identities and
the gate are untouched.

Scored per *field*, not per cell, because that is what the decoder consumes: four
cells at 97.6% is 90.7% if the errors are independent, and the question is whether
reading them together beats that.

Usage:
  python3 tools/strip_model.py cv    # held-out comparison against the cell reader
  python3 tools/strip_model.py fit   # fit on everything -> .cache/strip_cnn.pt
"""
import os, sys
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

STRIPS = ".cache/digit_strips.npz"
OUT = ".cache/strip_cnn.pt"
W, H, NDIG = 128, 36, 4
EPOCHS = 30
BATCH = 128
MAX_STEPS = int(os.environ.get("PV_STRIP_STEPS", "400"))
torch.set_num_threads(max(1, os.cpu_count() or 1))


class StripNet(nn.Module):
    """Convolutional trunk, then one classifier head per digit position.

    Four heads rather than a recurrent decoder: the field is a fixed four digits
    in fixed places, so there is no alignment problem to solve and nothing for a
    sequence model to buy. The trunk is shared, which is the whole point — every
    head sees the entire field.
    """

    def __init__(self):
        super().__init__()
        c = [1, 32, 64, 128]
        self.b1 = nn.Sequential(nn.Conv2d(c[0], c[1], 3, padding=1),
                                nn.BatchNorm2d(c[1]), nn.ReLU(),
                                nn.Conv2d(c[1], c[1], 3, padding=1),
                                nn.BatchNorm2d(c[1]), nn.ReLU(), nn.MaxPool2d(2))
        self.b2 = nn.Sequential(nn.Conv2d(c[1], c[2], 3, padding=1),
                                nn.BatchNorm2d(c[2]), nn.ReLU(),
                                nn.Conv2d(c[2], c[2], 3, padding=1),
                                nn.BatchNorm2d(c[2]), nn.ReLU(), nn.MaxPool2d(2))
        self.b3 = nn.Sequential(nn.Conv2d(c[2], c[3], 3, padding=1),
                                nn.BatchNorm2d(c[3]), nn.ReLU(), nn.MaxPool2d(2))
        self.drop = nn.Dropout(0.3)
        feat = c[3] * (H // 8) * (W // 8)
        self.fc = nn.Linear(feat, 256)
        self.heads = nn.ModuleList([nn.Linear(256, 10) for _ in range(NDIG)])

    def forward(self, x):
        x = self.b3(self.b2(self.b1(x)))
        x = F.relu(self.fc(self.drop(x.flatten(1))))
        return torch.stack([h(x) for h in self.heads], dim=1)   # (B, NDIG, 10)


def augment(batch):
    """The same distortions the cell reader trains through, at strip scale."""
    n = batch.shape[0]
    ang = torch.empty(n).uniform_(-6, 6) * np.pi / 180
    scale = torch.empty(n).uniform_(0.92, 1.08)
    tx = torch.empty(n).uniform_(-0.06, 0.06)
    ty = torch.empty(n).uniform_(-0.10, 0.10)
    cos, sin = torch.cos(ang) / scale, torch.sin(ang) / scale
    theta = torch.zeros(n, 2, 3)
    theta[:, 0, 0], theta[:, 0, 1], theta[:, 0, 2] = cos, -sin, tx
    theta[:, 1, 0], theta[:, 1, 1], theta[:, 1, 2] = sin, cos, ty
    out = F.grid_sample(batch, F.affine_grid(theta, batch.shape, align_corners=False),
                        align_corners=False)
    thick = torch.rand(n)
    fat, thin = F.max_pool2d(out, 3, 1, 1), -F.max_pool2d(-out, 3, 1, 1)
    out = torch.where((thick < 0.2).view(-1, 1, 1, 1), fat,
                      torch.where((thick > 0.8).view(-1, 1, 1, 1), thin, out))
    # Resolution loss, as for the cells: the forms still unread are the degraded
    # ones, and a net trained only on sharp strips is out of domain on them.
    sizes = [(H // 3, W // 3), (H // 2, W // 2), (2 * H // 3, 2 * W // 3)]
    pick = torch.randint(0, len(sizes), (n,))
    deg = torch.rand(n) < 0.5
    for i, sz in enumerate(sizes):
        take = (deg & (pick == i)).nonzero(as_tuple=True)[0]
        if len(take):
            small = F.interpolate(out[take], size=sz, mode="area")
            out[take] = F.interpolate(small, size=(H, W), mode="bilinear",
                                      align_corners=False)
    return out + torch.randn_like(out) * 0.05


def load():
    d = np.load(STRIPS, allow_pickle=True)
    code = d["code"] if "code" in d.files else np.array([""] * len(d["y"]))
    return d["X"], d["y"].astype(np.int64), code


def train(X, y, epochs=EPOCHS, seed=0, log=False):
    torch.manual_seed(seed)
    Xt = torch.from_numpy(X).float().div(255).unsqueeze(1)
    yt = torch.from_numpy(y)
    net = StripNet()
    opt = torch.optim.AdamW(net.parameters(), lr=2e-3, weight_decay=1e-4)
    steps = min(MAX_STEPS, max(1, len(yt) // BATCH))
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, 2e-3, epochs * steps)
    net.train()
    for ep in range(epochs):
        idx = torch.randint(0, len(yt), (steps * BATCH,))
        tot = 0.0
        for s in range(steps):
            b = idx[s * BATCH:(s + 1) * BATCH]
            logits = net(augment(Xt[b]))
            loss = sum(F.cross_entropy(logits[:, i], yt[b][:, i], label_smoothing=0.05)
                       for i in range(NDIG)) / NDIG
            opt.zero_grad(); loss.backward(); opt.step(); sched.step()
            tot += loss.item()
        if log and (ep + 1) % 10 == 0:
            print(f"    epoch {ep+1:3d}  loss {tot/steps:.4f}", flush=True)
    net.eval()
    return net


@torch.no_grad()
def predict(net, X):
    """(N, NDIG, 10) probabilities — the shape FieldProbs already consumes."""
    Xt = torch.from_numpy(np.asarray(X)).float().div(255).unsqueeze(1)
    out = []
    for i in range(0, len(Xt), 256):
        out.append(F.softmax(net(Xt[i:i + 256]), dim=2))
    return torch.cat(out).numpy()


HOLDOUT = ".cache/strip_cnn_holdout.pt"


def cv(holdout=0.12):
    """Held-out split, with every strip from a pilot form withheld.

    The pilot is the only independent ground truth there is, so a model that has
    seen any of it cannot be scored against it. Grouping by form also stops a
    field from one scan training the net that reads another field of the same
    scan — the leak that made an early cell-classifier number 25 points too
    generous.
    """
    X, y, code = load()
    import json
    pilot = {json.loads(l)["bureau_code"]
             for l in open(".cache/pv_pilot/readings.jsonl", encoding="utf-8")}
    keep = ~np.isin(code, list(pilot))
    print(f"withholding {int((~keep).sum())} strips from {len(pilot)} pilot forms",
          flush=True)
    Xk, yk = X[keep], y[keep]
    rng = np.random.default_rng(0)
    idx = rng.permutation(len(yk))
    n = int(len(yk) * holdout)
    te, tr = idx[:n], idx[n:]
    print(f"train {len(tr)} strips, test {len(te)}", flush=True)
    net = train(Xk[tr], yk[tr], log=True)
    p = predict(net, Xk[te]).argmax(2)
    print(f"\nstrip reader:  per-cell {(p == yk[te]).mean():.4f}   "
          f"per-field {(p == yk[te]).all(1).mean():.4f}")
    print(f"cell reader:   per-cell 0.9758  per-field 0.9758^4 = "
          f"{0.9758**4:.4f} if its errors were independent")
    torch.save(net.state_dict(), HOLDOUT)
    print(f"-> {HOLDOUT} (never saw a pilot form)")


def fit():
    X, y, _ = load()
    print(f"training on {len(y)} strips", flush=True)
    net = train(X, y, log=True)
    torch.save(net.state_dict(), OUT)
    print(f"-> {OUT}")


if __name__ == "__main__":
    (cv if len(sys.argv) > 1 and sys.argv[1] == "cv" else fit)()
