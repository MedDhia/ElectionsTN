"""Read the candidate score from the words the form spells it out in.

This exists for one reason: `valid == zammel + maghzaoui + saied` is one equation
in three unknowns, so the identities that protect every other field on the form
cannot arbitrate between two splits that share a total. The words column can, and
it is the only independent evidence on the page that does.

The output is deliberately the same `(N, 4, 10)` array the digit readers emit, so
the decoder can weigh words against cells with the machinery it already has
rather than needing a second kind of evidence plumbed through it.

Scored by whole number rather than per digit, because a leading zero is free —
almost every score is under a thousand, so the thousands head is right by
default and per-cell accuracy flatters. The tens digit is reported separately
since that is where the confusions that survive the sum identity live.

The split is by *form*, not by strip. Three strips from one scan share a hand, a
pen and a scan; splitting within a form lets the model see two of them and be
tested on the third, which is not the question. (`strip_model.cv` splits within
non-pilot forms and its per-cell figure is optimistic for exactly this reason;
this one does not repeat that.)

Usage:
  python3 tools/word_model.py cv    # grouped by form, pilot withheld
  python3 tools/word_model.py fit   # -> .cache/word_cnn.pt
"""
import json, os, sys
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

STRIPS = ".cache/word_strips.npz"
OUT = ".cache/word_cnn.pt"
HOLDOUT = ".cache/word_cnn_holdout.pt"
W, H, NDIG = 512, 28, 4
EPOCHS = 30
BATCH = 96
MAX_STEPS = int(os.environ.get("PV_WORD_STEPS", "300"))
torch.set_num_threads(max(1, os.cpu_count() or 1))


class WordNet(nn.Module):
    """Convolutional trunk over the whole phrase, one head per digit position.

    Four heads rather than a sequence decoder: the target is a fixed four-digit
    number, and the alignment between Arabic number words and digit positions is
    not monotonic anyway — `ثلاثمائة و تسعة و ثمانين` says hundreds, then units,
    then tens. There is no left-to-right correspondence for a recurrent decoder
    to exploit, so a shared trunk that sees the whole phrase is the honest shape.
    """

    def __init__(self):
        super().__init__()
        c = [1, 32, 64, 128, 128]

        def block(i, o, pool):
            return nn.Sequential(nn.Conv2d(i, o, 3, padding=1), nn.BatchNorm2d(o),
                                 nn.ReLU(), nn.Conv2d(o, o, 3, padding=1),
                                 nn.BatchNorm2d(o), nn.ReLU(), nn.MaxPool2d(pool))
        self.b1 = block(c[0], c[1], 2)
        self.b2 = block(c[1], c[2], 2)
        self.b3 = block(c[2], c[3], 2)
        self.b4 = block(c[3], c[4], 2)
        self.drop = nn.Dropout(0.3)
        self.fc = nn.Linear(c[4] * (H // 16) * (W // 16), 256)
        self.heads = nn.ModuleList([nn.Linear(256, 10) for _ in range(NDIG)])

    def forward(self, x):
        x = self.b4(self.b3(self.b2(self.b1(x))))
        x = F.relu(self.fc(self.drop(x.flatten(1))))
        return torch.stack([h(x) for h in self.heads], dim=1)


def augment(batch):
    n = batch.shape[0]
    ang = torch.empty(n).uniform_(-3, 3) * np.pi / 180
    scale = torch.empty(n).uniform_(0.95, 1.05)
    tx = torch.empty(n).uniform_(-0.04, 0.04)
    ty = torch.empty(n).uniform_(-0.12, 0.12)
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
    sizes = [(H // 3, W // 3), (H // 2, W // 2)]
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
    return d["X"], d["y"].astype(np.int64), d["code"]


def train(X, y, epochs=EPOCHS, seed=0, log=False):
    torch.manual_seed(seed)
    Xt = torch.from_numpy(X).float().div(255).unsqueeze(1)
    yt = torch.from_numpy(y)
    net = WordNet()
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
        if log and (ep + 1) % 5 == 0:
            print(f"    epoch {ep+1:3d}  loss {tot/steps:.4f}", flush=True)
    net.eval()
    return net


@torch.no_grad()
def predict(net, X):
    """(N, NDIG, 10) probabilities, the shape the decoder already consumes."""
    Xt = torch.from_numpy(np.asarray(X)).float().div(255).unsqueeze(1)
    out = []
    for i in range(0, len(Xt), 128):
        out.append(F.softmax(net(Xt[i:i + 128]), dim=2))
    return torch.cat(out).numpy()


def cv(holdout=0.15):
    X, y, code = load()
    pilot = {json.loads(l)["bureau_code"]
             for l in open(".cache/pv_pilot/readings.jsonl", encoding="utf-8")}
    keep = ~np.isin(code, list(pilot))
    print(f"withholding {int((~keep).sum())} strips from {len(pilot)} pilot forms",
          flush=True)
    Xk, yk, ck = X[keep], y[keep], code[keep]
    forms = np.unique(ck)
    rng = np.random.default_rng(0)
    forms = rng.permutation(forms)
    nte = int(len(forms) * holdout)
    test_forms = set(forms[:nte])
    te = np.array([c in test_forms for c in ck])
    print(f"train {int((~te).sum())} strips from {len(forms)-nte} forms, "
          f"test {int(te.sum())} from {nte}", flush=True)
    net = train(Xk[~te], yk[~te], log=True)
    p = predict(net, Xk[te]).argmax(2)
    t = yk[te]
    print(f"\nword reader:   per-digit {(p == t).mean():.4f}   "
          f"whole number {(p == t).all(1).mean():.4f}")
    print(f"  tens digit   {(p[:, 2] == t[:, 2]).mean():.4f}"
          f"   units {(p[:, 3] == t[:, 3]).mean():.4f}"
          f"   hundreds {(p[:, 1] == t[:, 1]).mean():.4f}")
    torch.save(net.state_dict(), HOLDOUT)
    print(f"-> {HOLDOUT} (never saw a pilot form)")


def fit():
    X, y, _ = load()
    print(f"training on {len(y)} word strips", flush=True)
    net = train(X, y, log=True)
    torch.save(net.state_dict(), OUT)
    print(f"-> {OUT}")


if __name__ == "__main__":
    (cv if len(sys.argv) > 1 and sys.argv[1] == "cv" else fit)()
