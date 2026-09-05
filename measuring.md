# Instruments in this repo, and how each one would lie

This project is nothing but measurement, so this file is the part of it that
matters. Every number the bench reports has an entry in `src/bench/methods.py`
saying what it measures, how it would be wrong, and what would catch it. That
registry is the source; this file is the history and the standing warnings.

Read it before trusting a number that came out of `src/bench/`.

## The rule this file exists for

Carried over from the previous project, where seven instruments were wrong
inside a week and every one of them passed its own check:

> A check that agrees with itself proves nothing about the thing it is checking.

and its companion:

> When one run disagrees with thirty, look at the one before dismissing it.

There is a second form of it, found here on the first day, which that project had
not run into: documentation can agree with an instrument, and both can be wrong.
Entry 1 below is a false claim about working code. No test suite can find that
class of error, because the suite tests the code and the code was fine.

## What is different here

On that project the failures were flaky: a fault would show on some fraction of
runs, so the question was how many runs are enough, and the arithmetic
`p^n + (1-p)^n` was the answer.

None of that applies here. A measurement of a file is a pure function of that
file. Running it four times and getting the same number proves nothing at all,
because a wrong instrument is wrong identically every time. Repetition is not a
backstop in this repo and should never be offered as one.

What replaces it is two things, and both are required before a number ships:

1. **A second instrument.** Where the number can be computed a different way, it
   is, and the bench reports the disagreement rather than averaging it. LUFS and
   true peak have an independent implementation written from the recommendation
   rather than from the first implementation.

   Where it cannot, that is said out loud. The spectral figure has no runtime
   second instrument, because the whole file transform is exact and every other
   method measures through a response that is not ideal. Two candidates were
   built and both failed, which is entries 9 and 10. A number with no second
   opinion is not the same as a number that has one, and the registry says which
   is which.
2. **A control that proves the check can fail.** Every assertion is paired with a
   value it must reject, and `rig.rejects` raises `Toothless` if it accepts one.
   `tools/mutate.py` does the same at the level of the whole suite: it breaks the
   engine on purpose and exits non zero if no test notices.

## Observed here

### 1. The cross check that could not see the thing it was written for

**2026-08-26, `src/bench/methods.py`.**

`decode/native-rate` documented its cross check as decoded frames divided by the
decoded rate, against the duration the container claims, and said this catches a
loader that resamples to 22050.

It does not. A resample to half the rate halves the frame count and halves the
rate, and `n/2` frames at `r/2` Hz is the same number of seconds. The check sat
in the registry as the named defence against the exact failure it is blind to.

What actually catches an honest resampler is the other comparison: the rate the
decoder reports against the rate ffprobe read from the container. Those come from
two different places. The duration check is still load bearing, but for different
faults: a truncated decode, and a decoder that resamples while still claiming the
source rate.

**Caught by** writing `tools/mutate.py` and having to say, per mutation, which
check was supposed to fire. Mutation A and mutation B are the same resample and
they are caught by different checks, and the registry described only one of them.
Nothing in the test suite would ever have found this, because the suite tests the
code and this was a false claim about the code.

**Fixed in** `methods.py`: both checks named, and the blind spot written down as a
failure mode rather than left out.

### 2. The peak that is linear, in a range where decibels would look right

**2026-08-26, `src/bench/measure/ebur128.py`.**

ffmpeg's ebur128 publishes its figures twice. The Summary block prints one decimal
place, the frame metadata prints three, so the obvious move is to read everything
from the metadata. That is right for loudness and wrong for peaks, for two
separate reasons.

`lavfi.r128.true_peak` is linear amplitude, not decibels. A file peaking at
2.9 dBTP publishes `1.401`. Read as decibels that is 1.4 dBTP: wrong by 1.5 dB,
in the right range to look like a real answer, and comfortably inside a -1 dBTP
target that the file is in fact 3.9 dB over.

The three decimals are also decimals of amplitude, so what they are worth in
decibels depends on the level. At a peak near 1.0 they are 0.009 dB. At a peak of
0.009 they are 0.5 dB. Below about -66 dBFS the metadata cannot represent the peak
at all and prints `0.000` for a peak the Summary reports perfectly well.

So the precision inverts: the metadata is the better number for loudness and the
Summary is the better number for peaks below roughly -21 dBFS. Peaks are read from
the Summary and checked against the metadata, the opposite way round from the
loudness figures, and the tolerance for that check is derived from the
quantisation at the level in question rather than being a constant.

**Caught by** the guard that compares the two, on a file 40 dB down, where it
refused a 0.2 dB gap it had no account for. The guard was written for a different
reason and found this instead.

### 3. The absence rule that read a coarse copy to decide a fine value existed

**2026-08-26, `src/bench/measure/ebur128.py`.**

Having moved the peaks to the Summary, the rule deciding whether a peak exists at
all was still reading the metadata: absent when `true_peak <= 0`. On material
peaking at -86 dBFS the metadata prints `0.000`, because three decimals of
amplitude cannot hold it, so the bench reported no peak for a file whose peak the
Summary had printed as -85.9.

The independent instrument reported -85.885, the primary reported nothing, and the
cross check dutifully listed it under `only_one_instrument_reported`. The bench was
faithfully reporting a disagreement it had manufactured itself.

**Caught by** the calibration run, on the one case quiet enough to trigger it.
**Fixed in** `ebur128.py`: existence is decided by the field the value is read
from, and the metadata guard is skipped where the metadata cannot represent the
number.

### 4. The control that was not the signal I thought it was

**2026-08-26, `tests/test_loudness.py`.**

The true peak control is a sine at a quarter of the sample rate, phased so every
sample sits at amplitude over root two. The continuous signal peaks at the
amplitude, 3.01 dB above every sample in the file, so an instrument that quietly
returns sample peak reads 3 dB low and the control catches it.

The first version of that signal started abruptly, mid waveform, and its analytic
peak is not the amplitude. A gated sine is a sine plus a step, the step is
wideband, and any reconstruction rings around it: an independent 32x oversampler
put the real peak 0.1 dB above the amplitude, and ffmpeg, whose interpolator is
shorter, put it 0.5 dB above. I was one step from recording ffmpeg as reading
0.59 dB high against an analytic answer that did not describe the file I had built.

With a raised cosine fade at each end, ffmpeg reads the analytic answer to three
decimal places and the independent implementation to within 0.0005 dB.

**Caught by** checking a suspicious disagreement against a third instrument before
writing it down rather than after.
**Left in** as `test_a_discontinuity_makes_them_disagree_about_true_peak`, which is
now the control proving the disagreement flag can fire at all. The half decibel is
real. It is a fact about files with hard starts and hard edits, not a fault in
either instrument, and it is reported rather than averaged.

### 5. The test that named one gate and exercised the other

**2026-08-26, `tests/test_loudness.py`.**

`test_material_below_the_absolute_gate_is_excluded` appended 20 s of material 60 dB
below a tone reading -6 LUFS. That material reads -66 LUFS, which is above the
absolute gate at -70. It was excluded by the relative gate, and the test would have
passed with the absolute gate deleted.

Two gates, one test, and the name pointed at the one that was not doing the work.

**Caught by** writing the mutation that deletes the relative gate and having to
predict which test would fire.
**Fixed in** `tests/test_loudness.py`: 80 dB down for the absolute gate, 60 dB down
for the relative gate, each asserting the block counts that prove which mechanism
ran, and one shared control at 5 dB down that passes both gates and must be
refused.

### 6. The registry scan that could not see its own constant

**2026-08-26, `tests/test_methods.py`.**

The check that every method id used by the engine is documented scanned for
constants with a pattern that required at least one character before the word
METHOD. It matched `PROBE_METHOD` and `DECODE_METHOD` and was blind to a constant
named exactly `METHOD`, which is what all three loudness modules use.

It failed loudly rather than passing quietly, but only because the other half of
the same check noticed three documented methods that nothing appeared to compute.
A registry check with only the orphan half would have said nothing at all.

**Caught by** the reverse direction of the same test.
**Fixed in** `tests/test_methods.py`: match any capitalised constant, then filter
by name.

### 7. The band edges that moved when the window length changed

**2026-08-26, `src/bench/measure/spectral.py`.**

Band energy was summed by taking every FFT bin whose centre falls inside the band.
Band edges do not land on bin edges, so each band is quantised to whole bins and
gains or loses up to half a bin at each end. On a narrow band that is a bias of one
or two percent, and its size and sign depend on the window length.

Measured on a flat spectrum, where the 60 Hz to 250 Hz band is exactly 0.951
percent of the 20 Hz to 20 kHz denominator:

```
nperseg    whole bins    bins weighted by overlap
  2048       0.961               0.942
  4096       0.962               0.944
  8192       0.935               0.943
 16384       0.935               0.943
 32768       0.938               0.939
```

The left column is not noise. It is two groups, set by where the bin edges happen
to fall, and it would have moved the reported percentage by 0.03 points if anyone
had ever tuned the window length for an unrelated reason. Every one of those
readings summed to 100 across the band set.

**Caught by** running the same measurement at five window lengths and comparing
against a signal whose answer is known from the band widths alone. A single window
length would have shown nothing, and so would agreement between two estimators
using the same edge rule.

**Fixed in** `spectral.py`: each bin is weighted by how much of it lies inside the
band. The residual spread across window lengths is 0.01 points, which is what sets
the two decimal places the percentages are printed to.

### 8. The band edge that a 15 Hz tone walked straight through

**2026-08-26, `src/bench/measure/spectral.py`.**

A test asserted that content below 20 Hz stays out of the bands, since the
denominator starts at 20 Hz. It failed. A 15 Hz tone added to a flat signal moved
the 20 Hz to 250 Hz rollup from 1.15 percent to 87.9.

Not a coding error. A Hann window's mainlobe is two bins either side of a tone,
and at 8192 samples a bin is 5.4 Hz, so the mainlobe reached 10.8 Hz past 15 Hz
and well over the edge. The narrowest band in the set is 40 Hz wide and the
window could not resolve its edges to better than a quarter of it.

Measured, tone at 15 Hz amplitude 0.3, shift in the 20 Hz to 250 Hz rollup:

```
nperseg    bin width    15 Hz tone    18 Hz tone
   8192      5.383 Hz      +87.59        +96.28
  16384      2.692 Hz      +23.80        +90.99
  32768      1.346 Hz       +0.06        +39.92
  65536      0.673 Hz       +0.00         +0.45
```

The window is now 65536 samples, chosen so that two bins is 1.35 Hz, 3.4 percent
of the narrowest band, rather than 27 percent. Flat spectrum accuracy is
unchanged at every one of those lengths, so nothing was traded for it except a
minimum file length of 1.49 s.

The 18 Hz column is the part that does not go away. Content sitting within a
couple of bins of a band edge belongs to both bands and no window length fixes
that. It is written down in `methods.py` as a limit rather than left to be
discovered by someone reading a sub band figure on a track with heavy rumble.

**Caught by** a test that asserted the obvious thing and was allowed to fail
rather than being loosened until it passed.

### 9. The approximate instrument was the primary and the exact one was the check

**2026-08-26, `src/bench/measure/spectral.py`.**

Band energy was measured with Welch, and a whole file transform was the cross
check. On the first run over real masters the cross check flagged 6 files of 14,
by as much as 0.84 points on a band.

Two explanations were tested and both were wrong. The two estimators do not
measure different spans: trimming the transform to exactly the span Welch used
moved the disagreement from 0.830 to 0.809. The file end discontinuity is not
responsible either: a 50 ms fade at each end moved it by 0.0001.

The cause is that the two answer different questions. Welch estimates the power
spectral density of a stationary random process. This bench asks how much energy
this file has in this band, and by Parseval the transform of the whole file
answers that exactly rather than approximately. Welch's window mainlobe shares
energy across band edges, and real music puts a great deal of energy at 60 Hz and
120 Hz, which is where band edges are. Growing the window makes Welch converge on
the transform:

```
nperseg      bin width     20-60 Hz    60-120 Hz
  65536       0.7324 Hz      40.221       23.985
 262144       0.1831 Hz      40.577       23.743
1048576       0.0458 Hz      41.152       23.089
transform     0.0048 Hz      41.041       23.157
```

The two tone control had already said this and it was not acted on. On a split
whose analytic answer is 94.1176, the transform returned 94.1176 and Welch
returned 94.1163. That is the exact instrument and the approximate one, and they
were the wrong way round for two days.

**Caught by** a cross check firing on real material and refusing to be explained
away. Two plausible explanations were measured and killed before the real one.

**Fixed in** `spectral.py`: the whole file transform is the reported figure, zero
padded up to a fast length so no audio is dropped at all rather than truncated
down. Welch is gone rather than demoted, because the same measurement computed
less exactly is not a second opinion. One more thing was wrong and went with it:
the one sided spectrum had no doubling, which under weighted direct current and
Nyquist against every other bin. It only moved the outside the denominator
figures, and it was still wrong.

### 10. The filterbank that could not be a second opinion

**2026-08-26, `tests/filterbank.py`.**

With Welch gone the spectral figure had no second instrument, so a time domain
filterbank was the obvious replacement: filter into the bands, measure energy, no
transform anywhere, nothing shared with the transform path.

Built twice. Butterworth order 8, band energies as differences of cumulative
lowpass energies, read 84.71 on a control whose analytic answer is 94.1176, and
sat 7.3 points from the transform on a real file. That is a soft filter, not a
fair test of the idea, so it was built again properly: elliptic, decimated so the
numerics hold at a 20 Hz cutoff, orders 8 through 20. The transition at the 60 Hz
edge tightens exactly as it should:

```
order    -60 dB at    transition
    8      79.02 Hz     19.02 Hz
   12      66.26 Hz      6.26 Hz
   16      62.02 Hz      2.02 Hz
   20      60.66 Hz      0.66 Hz
```

The accuracy does not follow. On the two tone control, order 12 reads 94.1469,
order 16 reads 95.8101 and order 20 reads 96.2415, against 94.1176. It gets worse
as the filter gets sharper, because the floor is not transition width but
passband ripple: 0.05 dB of ripple is 0.6 percent in amplitude and 1.2 percent in
energy, and a higher order elliptic ripples more times across the passband. On a
real file it lands 0.64 to 0.94 points from the transform, no better than Welch,
at four times the cost.

The conclusion is not about filter design. For this quantity there is no
independent instrument that is equally exact, because the transform of the whole
file is exact and everything else measures the signal through a response that is
not ideal. A filterbank makes the same category error Welch made, more slowly.

**Fixed by** not shipping it. `methods.py` states plainly that this figure has no
runtime second instrument and why, which is the first number in this bench that
has none. What stands in its place is three analytic controls, a per band round
trip through the inverse transform that ends in the time domain, and the
filterbank kept in the tests at order 12 on controlled signals only, where
nothing sits near a band edge and it agrees to 0.03 points.

### 11. Coverage that existed by accident, and left the same way

**2026-08-26, `tests/test_spectral.py`.**

The other entries here are instruments that agreed with themselves. This one is
different: nothing was wrong, and the suite got weaker anyway.

When Welch was removed in entry 9, its tests went with it. One of them,
`test_window_length_does_not_change_the_percentages`, had been the only thing
holding the band edge weighting in place. It was never written for that. It
measured one band at two window lengths, and it happened to catch whole bin
assignment because Welch's bins were coarse enough for the bias to show.

With the transform as the primary a bin is five thousandths of a hertz. Weighting
each bin by its overlap with the band is then worth less than a thousandth of a
point, so no measurement the bench makes on any real file can tell it from
assigning whole bins by their centre. The arithmetic still decides the answer, and
on a one second file it decides it visibly.

The suite stayed green through all of it. Seventy one tests passed. Nothing in
that number said a check had gone.

The second survivor is a different fault with the same shape. Doubling every bin
including direct current and Nyquist is invisible in every percentage, because a
uniform factor cancels in a ratio. Only Parseval can see it, and only if direct
current or Nyquist actually carry energy. Every control signal in the suite was
built from tones and shaped noise and had neither. The test that would catch it
existed, ran, and passed. The signal it ran on could not contain the fault.

**Caught by** `tools/mutate.py`, and by nothing else. Both were reported as
SURVIVED against a green suite, which is the only form of evidence available for
a check that is missing rather than wrong.

**Fixed in** `tests/test_spectral.py`: `band_power` is now checked directly on a
synthetic spectrum with 7 Hz bins, where weighting by overlap gives 40 and whole
bins give 42, and there is a Parseval control on a signal built mostly out of
direct current and Nyquist.

Two things follow, and both are the point of this file.

`mutate.py` is not an audit that was run once when it was written. Coverage moves
whenever an instrument is removed or replaced, in ways nobody plans, and a passing
suite is silent about it. It runs after every change to the engine, and a
SURVIVED line is treated as a failure.

And the sharper half: **a control that cannot contain the fault cannot fail.**
Tolerances get the attention because they sit right there in the assertion. The
material a control runs on is chosen earlier, written once, and never looked at
again, and it decides which faults are visible at all.

### 12. The same error, invisible in one question and decisive in the other

**2026-08-27, `src/bench/measure/spectral.py`.**

Replacing Welch with the transform, entry 9, changed the reported figures. Across
thirteen real files:

```
                              under 250    60 to 250    20 to 60
largest move                       0.14         0.88        0.82
```

One instrument, one error, one set of files, and the size of the error depends
entirely on which figure is read off it. Welch was sharing energy across the 60 Hz
band edge in both directions. A rollup that spans that edge absorbs the error
almost completely. The two bands either side of it carry all of it.

That matters here and not in the abstract. The guaracha profile is written as a
percentage under 250 Hz, a rollup, so the wrong instrument was very nearly
harmless for it: 0.14 points on a range about eight points wide. The boom bap
profile rests on the 60 to 250 band, which is the exact figure the same wrong
instrument got wrong by 0.88.

Had the bench been checked against the guaracha profile alone, Welch would have
looked accurate enough to keep, and it would have been quietly wrong about the
only band the other profile cares about.

**Caught by** diffing what the swap moved, per file and per band, rather than
letting the new numbers replace the old ones without anyone looking at the
difference.

The rule this leaves: **"close enough" is not a property of an instrument.** It is
a property of an instrument and a question together, and the same error can be
noise for one reader and disqualifying for the next. An error budget quoted
without naming the figure it applies to says nothing at all. Every tolerance in
this repo is attached to a named quantity for that reason, and a tolerance that
looks generous on a rollup can be unusable one level down. When a target names a
band rather than a rollup, the tolerance that matters is the band's.

### 13. The change that entry 12 stopped before it shipped

**2026-08-27, `src/bench/measure/bs1770.py`.**

Every other entry here explains something after it went wrong. This one records a
change that was proposed, measured, and not made.

True peak is taken with an 8x oversampling filter of 257 taps, and it was costing
131 s of the 170 s a fifteen file run spends on loudness. The design sweep had 129
taps reading the analytic intersample control at +0.0000 dB, identical to 257, so
halving it looked like speed for nothing. It was measured across all fifteen real
files first, because the only genuine true peak disagreement this bench has ever
seen was on material with a hard edit in it, and a synthetic control cannot
contain that.

```
track                            257 taps   129 taps    d129-257
Ledger_x_Settled_MASTER_EQ        -1.0163    -0.9869    +0.02943
Ledger_x_Settled_MASTER           -1.1108    -1.1034    +0.00739
Pull_me_under 24 bit              -1.5028    -1.4977    +0.00506
Pull_me_under 48k 16 bit          -1.5027    -1.4979    +0.00480
the nine album tracks                                 under 0.003
total time                         106.8 s     76.5 s
```

The largest disagreement is 0.029 dB, a fifth of the 0.15 dB tolerance the two
loudness instruments are held to. By that measure it passes easily. But the file
it lands on reads -1.0163 dBTP at 257 taps and -0.9869 at 129, against a ceiling
of -1 dBTP. The two filter lengths give opposite answers to the only question
anyone asks of a true peak figure.

The pattern is not chance. The four largest disagreements are the four files
closest to full scale. **The instrument gets least certain exactly where the
question is asked**, because a master pushed to the ceiling has the densest
intersample activity around its peaks, and that is what filter length resolves. On
the nine album tracks sitting at -3.5 to -4.5 dBTP, where nobody is asking a
boundary question, the two lengths agree to under 0.003 dB.

**Not changed.** 257 taps stay. The saving was 30 s across 49 minutes of audio.

Two things this settles beyond the filter.

A tolerance is attached to one comparison and does not transfer to another. The
0.15 dB figure is for agreement between two instruments measuring the same file.
The -1 dBTP ceiling is a different comparison with a different budget, and nothing
in the code connected the two until this. When the target layer lands, a deviation
measured against a boundary has to carry the uncertainty of the measurement, not
just its value, or it will report a pass on a file sitting inside the error bar.

And the rule from entry 12 did the work here rather than being illustrated by it.
That is the first time in this file that a rule already written down stopped
something before it shipped instead of explaining it afterwards, which is the only
reason any of this is written down.

### 14. The suite that reported on a tree that was not the repository

**2026-08-27, `tools/mutate.py`.**

The suite came back 2 failed, 99 passed, and one of the named failures was
`test_material_below_the_relative_gate_is_excluded`. Nothing was wrong with the
code.

`mutate.py` patched source files where they sat. It was running at the time, and
one of its mutants is "drop the relative gate", which is the exact mutant that
test exists to catch. The suite was correct about the tree it ran on and had
nothing whatever to say about the repository, because for those few seconds the
tree was not the repository.

That reading is indistinguishable from a real regression. A named test, a
plausible mechanism, a red count. This is the same shape as the headless renderer
on the previous project, which measured a page the application never draws: a real
measurement of the wrong thing.

**Caught by** noticing that the failing test was the one the running mutant
targets, and then confirmed rather than assumed. After the run finished and the
tree was restored, the same suite passed 101.

**Fixed in** `mutate.py`: it copies `src`, `tests`, `tools` and `pyproject.toml`
into a temporary directory once, patches and runs pytest there, and never writes
to the working tree at all. The proof is that the suite now passes 101 while the
tool is mid run, with every source hash unchanged.

That also removes the worse version of the same hazard. The old tool restored each
file in a `finally` block and printed RESTORE FAILED if it could not. A crash at
the wrong moment left mutated source sitting in the tree with one printed line as
the only record.

The general form: **an instrument that modifies the thing under test makes every
other reading of that thing meaningless while it runs**, and the wrong reading
looks exactly like a fault. The fix is not to remember not to run two things at
once. It is to make the tool incapable of it.

### 15. The check I invented, ran once, and read as evidence

Ground truth for tempo did not exist for this material. Looking for some, I reasoned that a track rendered at a fixed project tempo should be close to a whole number of bars long, so I took each file's duration, divided by the beat period at the tempo asked for, and looked at how near the result sat to an integer number of bars.

Four of nine landed close. Two landed very close: Extension at 119 bars implies 132.492 BPM against 132.51 asked for, and Skip at 117 bars implies 136.020 against 136.00. I was one message from reporting that the request list was ground truth and that the deck, an independent analyser, was wrong by up to 0.65%.

Then I built the envelope and evaluated a single frequency transform of it at the beat rate and its second and fourth harmonics, over the whole file. Over 200 seconds that separates candidates 0.4 BPM apart cleanly. It picked the deck over the request list on 8 of 9, on three of them by a factor of 14 to 17. At the tempo it found, Extension is 118.67 bars long. The file does not end on a bar line at all.

The bar check had no control, and could not have had one in the form I used it. The bar count was a free parameter I fitted after the fact, so for almost any nearby tempo some integer bar count fits, and a small residual is what the method produces whether or not the tempo is right. I never asked what the check would say if the tempo were wrong. The answer is: roughly the same thing.

The ledger so far has been about instruments that agreed with themselves, and documentation that agreed with an instrument. This is a third kind. It is a check invented for one question, run once, and believed because its answer was the one I was hoping for. **A measurement with a free parameter fitted after the fact is not evidence, it is a curve drawn through a point.**

### 16. The rule that was winning because of a bug inside it

Four candidate scoring rules were compared for the whole file tempo peak. One of them, the fundamental divided by a local median of the score around it, matched the independent deck to 0.01 BPM on four of nine tracks, where the others were 0.2 to 0.3 BPM away. That is the kind of agreement that decides a design.

The local median window was computed by a leftover expression that had nothing to do with the span it was supposed to cover. Rewriting it to the intended plus or minus 20 percent in tempo turned the rule into a near copy of the plain fundamental, and its answers changed on four tracks.

The correct version is not better than the others. The bug was.

I would have shipped it on the strength of that agreement, and the justification I would have written down, that a peak measured against its local floor is more robust than a raw peak, would have been reasonable prose about a mechanism that was not running. **An instrument that outperforms its rivals is a reason to read its code, not a reason to pick it.**

### 17. The robust threshold that is exactly zero on the material it is for

Onsets are local maxima of the envelope above a threshold. I used the standard robust form: the median plus a multiple of the median absolute deviation.

On a click track at 128 BPM with 257 clicks it detected 935 onsets. On the envelope of that track most samples sit at exactly the same floor, because between hits the spectral flux is exactly zero. The median absolute deviation of that envelope is exactly zero. The threshold collapses to the median, which makes it the least selective threshold available, and every scrap of floating point dust above the floor becomes an onset.

The failure only appears on clean material. On the nine real tracks the envelope is never sparse, the deviation is comfortably nonzero, and the threshold behaves. Had I only ever run it on real music it would have looked correct.

The replacement is the median plus a multiple of the mean positive excursion, which cannot be zero for any signal with an onset in it. **A robust statistic is robust against the thing it was designed for, and a sparse signal is not that thing.**

### 18. The control that was not the signal I thought it was, from the other side

Entry 4 was a control that contained more than I intended: an abruptly started sine is a sine plus a step. This is the same fault at the other end of the sample.

Every click in my synthetic control was detected exactly twice, at every tempo, 288 detections for 144 clicks and 700 for 350. Exactly double is structural, so I went looking for the pair. The second detection sits about 130 ms after the first at roughly half its height. 130 ms was the length of my synthetic kick, whose exponential decay was truncated at 5 percent of full amplitude and then stopped. That step is a real broadband transient and the detector was right to see it.

I was about to change the onset detector to suppress something my own control genuinely contained.

The fix belonged in the signal: hits now decay for nine time constants with a raised cosine over the last quarter. Same lesson as entry 4, and it did not transfer on its own. Knowing that abrupt starts are a trap did not make me check the ends.

### 19. The fit number that cannot exceed its own tolerance

Grid fit is the median distance from an onset to the nearest grid tick, in milliseconds. Onsets further than 30 ms from a tick are not on the grid and are excluded, which is what makes the number meaningful.

It is also what caps it. The median of a distribution truncated at 30 ms cannot exceed 15 ms. Measured on a click track with scatter of 0, 10, 20 and 40 ms, it reads 4.07, 9.09, 11.18 and 15.52 ms. Doubling the scatter from 20 to 40 moves it by 4 ms. Coverage over the same four is 1.000, 0.992, 0.852 and 0.570 and keeps separating them.

The negative control is what caught it. `rejects` was asked to confirm that a track jittered by 20 ms does not read as sitting on the grid, and it refused: 11.18 was inside the threshold I had chosen, so the check could not fail and proved nothing.

This matters more than it first looked. On the nine real tracks grid fit reads 7.96 to 15.85 ms, so it is at or near its ceiling on eight of nine. The number is saturated exactly where it was supposed to be useful. It is reported with coverage next to it, and the ceiling is written into the registry, because **a number with a ceiling reads like a measurement right up to the point where it stops being one.**

### 20. The second stage that resolved the octave worse than no second stage

Whether a track is at 72 with hats on every half beat or at 144 with hats on every beat is not answerable from the signal. Both grids fit. I built a second stage to try anyway: fit the onsets to each octave candidate and score by occupancy, the fraction of ticks that carry an onset, against coverage, the fraction of onsets that sit on a tick.

Against 35 controls with known answers, the whole file peak alone gets 27. Adding the grid fit stage gets 25. It changed two right answers to wrong and fixed none.

The reason is not a defect in the measure. For a kick every beat at 72 with a hat every half beat, the grid at 144 has occupancy 1.00 and coverage 1.00. It is a perfect fit, because events really do occur 144 times a minute. The measure is correct and the question is not a measurement question.

The stage stays, reporting fit quality, and does not choose. The chosen tempo comes from the whole file peak, whose failure rate is written down: 8 of 35, every one a doubling between 72 and 88 BPM on subdivided material, which is the region three of the nine tracks sit in. The alternatives are printed with their occupancy and coverage so the choice is visible.

**Adding an instrument is not the same as adding information, and a stage that is individually correct can still make the answer worse.**

### 21. The uncertainty that understated, and the horizon that had to be measured

Drift is a quadratic fit of beat index against time, so its uncertainty follows from the fit covariance. Reporting drift whenever the fitted span exceeded that uncertainty put drift on steady synthetic tracks: span 0.036 BPM against an uncertainty of 0.019.

The covariance assumes independent residuals. The obvious suspect was correlation between onset timing errors, so I measured it. Lag one autocorrelation is 0.17 across every control, steady and ramped, which inflates the uncertainty by 1.19. Steady controls still reached 2.6 times their uncertainty. Correlation was not the explanation. The excess is small systematic structure in the material that a quadratic partly absorbs, and no correction of the noise model reaches it.

So the horizon is measured rather than derived. Across eight steady controls at 90 seconds the largest span was 0.071 BPM, and drift is reported only above 0.1. The fit's own uncertainty is still reported, next to the floor, labelled as what it is.

This was the condition set before the feature was written: drift declares its horizon or it does not ship. It declares 0.1 BPM. The tracks it is for move by 0.14 to 3.00, so the horizon is outside them, and one track sits close enough to it to be worth saying out loud. **An uncertainty a model computes for itself is a statement about the model, not about the measurement.**

### 22. The range that was zero for anything that came back

Drift fits a polynomial to beat index against time and reports the tempo range. I evaluated the fitted tempo at the first fitted onset and the last, and reported the difference.

Ground truth for this did not exist until a tempo map could be written into a MIDI file and read back out of it. The first run of that set: a steady track read 0.00 against a true 0.00, two straight ramps read within 0.02, and an arch rising from 120 to 126 and back to 120 read **0.00 against a true 6.00**. Not a wrong range. No range at all: the field is absent and the report says steady.

The endpoints of an arch are the same number. Their difference is exactly zero however well the curve fits the middle, and a perfect fit produces it just as reliably as a bad one.

My first move was wrong. I assumed the fit was too stiff and swept the polynomial order. It does not help, because the order was never the problem: order 2 gave 0.00, order 3 gave 0.19, order 5 gave 0.45 against a true 6.00, and the horizon on steady material degraded from 0.071 to 0.894 on the way. I spent that sweep improving a model whose output was being read at two points where it could not differ.

Taking the smallest and largest the fitted tempo reaches anywhere across the span, the same order 3 fit reads 6.46. The change is four lines and the model is untouched.

Two things worth keeping. The first is that the bug was invisible to every control I had, because every synthetic drift I had built was a straight ramp, and for a monotonic shape the endpoints are the extremes. **A control set that only contains monotonic cases cannot see a fault that only appears when something returns.** The known answer set found it on its first run, which is the whole argument for building one.

The second is the shape of the failure. Sixteen entries in this file are about numbers that were wrong. This one was not wrong, it was missing, and a missing drift field reads as good news. The bench was telling me a track that moves 6 BPM is steady, in the same words it uses for a track that genuinely is.

### 23. The search range that was an octave prior with no entry in the registry

Tempo is found as the strongest rate in a search grid running 55 to 200 BPM. I wrote that range as a practical bound on where to look and described it nowhere, because a search window did not feel like a decision.

Seeding the guaracha target meant measuring the two references, and one of them came back at 199.99 BPM. The grid is `arange(55, 200, 0.01)`, whose last point is 199.99. That number was not a peak. It was the edge of my window, and the score was still climbing when the window ran out. Scanning 40 to 400 BPM put the real peak at exactly 200.00.

The other reference is worse, because it looks right. Bam Bam reports 122.00, which is a sensible tempo for the track. Over 40 to 400 its strongest rate is 244.00 at score 0.3453, against 0.3213 for 122.00. The bench reports the musically reasonable answer, and the thing that produced it was the range clipping the stronger peak away. The registry entry for tempo already admits the octave is a musical judgement and lists the alternatives. It said nothing about a second, larger octave decision happening one line earlier, in a constant that reads like an implementation detail.

Two separate faults, and only one of them shows.

The fix is small: a peak at either end of the grid is not a maximum, so the reported rate falls back to the best interior turning point, and the file carries a caveat saying a stronger rate lies outside the range and that the range chose the octave. Raka Taka Taka now reports 100.00 with that caveat. Bam Bam reports 122.00 without one, which is still the range's choice rather than the signal's, and the registry now says so.

What I had was not a bug in a calculation. Every line did what it said. **A search window is a prior, and a prior that is not written down is one nobody can disagree with.** Entry 1 was documentation that agreed with an instrument and both were wrong. This is an instrument whose most consequential decision was not in the documentation at all, because it did not look like a decision.

It also took a target to find. Nine of my own tracks and 35 synthetic controls went through this code without touching the edge, because every one of them sits comfortably inside 55 to 200. The first file from outside that set found it immediately.

### 24. Two mechanisms that were still there after the problem had moved

A mutation run left three survivors. None of them was a missing test in the way survivors usually are, and two of them said the same thing about the code.

**The shelf invariance was not coming from where the registry said it was.** Removing the per band normalisation entirely, so the eight band fluxes are simply summed, changed nothing the control could see: the tempo moved 0.000 BPM under every 2 dB shelf, with and without it. The registry said in as many words that dividing each band by its own mean is what makes the reading immune to a shelf, and the control that proves it uses a 2 dB shelf, and at 2 dB the claim is untestable because both forms are invariant.

The reason is one I had already worked out and then forgot. Flux is a difference of log magnitudes. A static gain adds a constant to the log, and a constant cancels in a difference. The invariance is a property of the flux, not of the normalisation.

The normalisation is not useless. Over 60 shelved renders across synthetic and real material the raw sum moves up to 0.120 BPM and the normalised envelope moves 0.000, but only from 6 dB upward. So the mechanism is real and the control was too gentle to reach it. The control now shelves at 12 dB and the tolerance is 0.03 BPM rather than 0.1, because the thing it is checking moves by exactly nothing.

Two faults in one place. The claim named the wrong mechanism, and the control could not have caught that because it was set below the level where the two differ. **A control calibrated to the value you expect cannot distinguish the mechanism you named from the one actually running.**

This is the same shape as entry 22, and the pair of them is worth holding together. There, every synthetic drift I had built was a straight ramp, and for a monotonic shape the two endpoints are the extremes, so a control set made only of ramps could not contain a fault that appears when the tempo comes back. Here the shelf is 2 dB, and the normalisation it is meant to test does not act until 6. Entry 11 stated the general form: a control that cannot contain the fault cannot fail.

These two are a narrower and more avoidable version of it, because in both cases the level was a number I chose. Not a shape I failed to imagine, not a component I did not know about. A ramp rather than an arch, and 2 dB rather than 12, both picked because they were the ordinary case. **Choosing a control at the level you expect to see puts it below the level where the mechanism it names does anything.**

**The annealing was solving a problem that had already been fixed elsewhere.** The onset matching tolerance started near half a beat and tightened over twelve rounds. That was added because a constant tempo starting model lost lock on anything moving more than about one beat per minute. It was then made unnecessary by initialising from a coarse tempo trajectory, which is a different fix for the same fault, and I kept both.

Measured across four drift shapes, the annealed schedule and a fixed tolerance agree to three decimals, and one refit round reaches the same answer as twelve. The whole schedule was inert. It has been replaced by refitting until the set of matched onsets stops changing, which removes two constants and the arbitrary count with them.

The mutation tool could only tell me that nothing noticed. It could not tell me whether that was a missing test or a mechanism doing nothing, and those want opposite fixes: one adds a control, the other deletes code. Both of these looked identical in the report. **A surviving mutant is a question, not a verdict**, and the two answers here were "the control is too weak" and "the code is not needed".

The third survivor was ordinary missing coverage, and it earned its own small lesson. A page test asserted that a missing value renders as a dim marker by looking for that marker anywhere in the HTML. Another part of the page emits the same marker for a different reason, so the assertion held even with the formatter mutated to print zeros. It now checks the formatter directly. The same shape as entry 11: coverage that existed by accident, and a control that passed for a reason unrelated to the thing it named.

### 25. Three answers to one question, two of them from an uncontrolled comparison

The mutation run came back 41 of 42, with one survivor: a mutant that was supposed to remove the onset fitting from the drift model. Entry 24 says a surviving mutant is a question. This is the record of getting that question wrong twice before answering it.

**First answer.** The mutant replaced twelve refit rounds with zero. It survived, and I read that as a design fault in the mutant rather than a finding, because there is still a final fit after the loop. So it removed one iteration of something I had already measured as converging in one iteration. Equivalent by construction, and I had built it that way myself.

**Second answer.** I rewrote it to return the windowed coefficients instead of the fitted ones, and measured the two. The windowed curve understated every ramp by twenty to twenty seven percent, and I wrote that down as the onset fit doing real work.

It was not. I evaluated the windowed curve across the range of the window centres and the fitted curve across the range of the onsets. The window centres start half a window in and stop half a window early, twenty five seconds narrower on a ninety second file, and the span of a rising curve is smaller over a shorter stretch. I compared two curves over two different intervals and reported the difference as a property of the curves.

**Third answer.** Over the same interval the two agree to 0.036 BPM on the known answer set and 0.013 on real material, against a floor of 0.4. That includes the case built to be hardest for a windowed estimate, eight bars with the drums out, where the gap is 0.005. The onset fitting does not shape the drift curve. The curve is the windowed estimate. What the onsets contribute is the stretch the curve is read over and the covariance, and neither of those is the thing the registry named.

So the mutant was right the whole time and I argued with it twice. It is now removed rather than fixed, because a mutation that provably changes nothing is not a coverage check, and leaving it in would make the tool fail forever for a true reason it cannot express.

Three mechanisms in this module have now turned out not to do what the file said they did: the per band normalisation in entry 24, the annealing in entry 24, and the onset fit here. All three passed every test. None of them was a wrong number.

The lesson that is new is about my own method rather than the code. Twice in a row I answered a question by measuring two things that differed in more than the one way I was studying. Entry 24 says choosing a control at the level you expect puts it below where the mechanism acts. This is the same fault moved into the comparison itself: **a difference between two measurements is only evidence about the thing you changed if it is the only thing that changed**, and an evaluation range is exactly the kind of thing that travels quietly with a change and gets read as its result.

### 26. Four boundaries, all missed the same way

The mastering layer decides a gain from a measurement and aims it at a target. Four faults came out of building it, and they are one fault seen from four sides: **a plan that arrives exactly at a boundary has not arrived inside it.**

**Aiming by half a step.** An uncertainty here is half the step a value is reported in. True peak is reported to 0.1 dB, so its uncertainty is 0.05. The first version aimed at `ceiling - uncertainty`, which puts the top of the measurement's interval exactly on the ceiling. `compare.verdict` calls that inside only because `-1.05 + 0.05` happens to land at `-1.0000000000000002` rather than at `-1.0`. The verdict was being decided by the last bit of a float. It now aims two uncertainties under, which is one whole reporting step of daylight, and a test asserts the daylight rather than the verdict.

**The limiter takes loudness the arithmetic cannot see.** The gain is worked out from the file's measured loudness. Then the limiter runs, and limiting removes loudness. The arithmetic has no way to know how much, because how much depends on the crest of the material inside the attack window. The first version predicted the loudness it would reach and missed by several LU. It now lifts the gain across measured passes and stops when the measurement says it is inside, not when a formula says it should be.

**Stopping on the condition you were derived from.** The correction loop above stopped when the reached loudness cleared the floor. Aiming at exactly the stop condition means aiming at the boundary the stop condition was derived from, where the comparison is again decided by the last bit. It now aims one uncertainty above the condition, so the loop stops with room rather than on the line.

**A prediction checked against the instrument that did not make it.** The plan is built in memory by the second instrument. The check read the primary instrument's number off the written file, found a gap the size of the two instruments' disagreement, and reported the plan as failed. The bench already reports that disagreement as its own field. The prediction now records which instrument made it and is checked against that one.

The first, third and fourth are the same mistake: a number was compared against a boundary without asking what the number's own uncertainty was, or which instrument drew the boundary. That is the thing this whole bench exists to stop, made in the layer built last.

### 27. A criterion that no setting could fail

The limiter's attack and release are chosen by search. The criterion is the one the user set: keep the output's spectral balance where the input's was. What the code checks is that every band's verdict against the target is unchanged.

On a synthetic test file that criterion accepted all twelve settings, including one that moved a band by 38 percentage points. The target used in that test bounds loudness and true peak and no bands at all. With no band bounded there are no verdicts to keep, so "no verdict changed" is true of everything, and the search reported `12 of 12 settings kept every band's verdict` while choosing between things it had not compared.

This is entry 11 again, in the one place I had not looked for it. A control that cannot fail proves nothing, and a **criterion** that cannot fail chooses nothing. The difference is that a control which cannot fail is silent, while this one printed a number that read like evidence.

The search now refuses when the target bounds no band or rollup, and says so in the plan: there is nothing here to choose a setting by, so none was chosen. Both shipped profiles bound ten bands and two rollups, so on real work the criterion is real. It took a target that bounds nothing to show that the code had never checked whether it had a criterion at all.

### 28. The clearance that cleared the wrong instrument's line

The plan is built from the second instrument measuring samples in memory. The verdict is taken from the primary instrument reading the written file. Those are two different numbers, and the bench already declares how far apart they are allowed to be before it complains: 0.15 dB on true peak, 0.05 LU on integrated loudness.

The plan cleared the ceiling by two of its own uncertainties, 0.1 dB, and aimed at -1.1 dBTP. The written file measured -1.1 by the second instrument and -1.0 by the primary. The verdict is taken from the primary, so the file landed on the line, and because the two instruments now disagreed by 0.1 the reported uncertainty grew to match, which pushed it further onto the line rather than less.

So a clearance derived from the input's own uncertainty cannot clear a boundary that a different instrument will draw on a different file. The clearance now adds the crosscheck tolerance the bench already declares for that field. It costs 0.15 dB of loudness on the peak and 0.05 LU on the loudness, and it is a number the bench already stands behind rather than one chosen to make this case work.

### 29. Measuring a file when the samples were in memory

`loudness.measure` runs the primary instrument over `audio.path` and the second instrument over `audio.samples`. The mastering layer wanted the loudness of the signal after its low cut, and got it with `loudness.measure(replace(audio, samples=filtered))`.

That measured the filtered samples with one instrument and the original file on disk with the other. The primary number was the unfiltered file. The gain was then derived from it, and the crosscheck delta, which is what the uncertainty is built from, was reporting the size of the low cut as instrument disagreement.

The output landed 0.15 dB under where the plan said it would, and the prediction check is what noticed. Nothing else could have: every number involved was plausible, and both instruments were working correctly on the inputs they were given.

The layer no longer calls `loudness.measure` on anything that is not a file. It has its own `second_instrument`, which takes samples and a rate, says in its result that it measured samples in memory with one instrument, and carries the reason in its docstring so the next person does not reach for the convenient call.

The general shape: **a dataclass field that is quietly a second source of truth.** `Audio` carries both samples and the path they came from, and `replace` makes it easy to change one and keep the other. `spectral.measure` reads only samples and is safe. `loudness.measure` reads both and is not. Nothing in the type says which.

### 30. The gain that turned down a file that was already right

If a target says a track should sit between -12 and -6 LUFS and a track sits at -9, there is nothing to do. The first version computed its gain as `low + clearance - measured` regardless, which for that track is -2.85 dB. It would have turned down every track already inside its target, to the bottom edge of it, and reported that as reaching the target.

Nothing caught this because the test file was well below the range, which is the case the layer was written for and the only one it was ever tried on. It now places the file against the bound first and refuses when the file is already inside, and when it is outside it aims at the near edge rather than always at the bottom.

The reason this is worth an entry is not the arithmetic. It is that the layer was built, run, and read on one file, and one file cannot show you what a rule does to the cases it was not built from. That is the same standing warning as the target profiles, which is why `evidence.n` is on the page.

### 31. A safety net that could not fire, and a reduction that arrived late

Two findings in the limiter, from writing its first controls.

**The elementwise minimum.** The last line of the gain envelope took the minimum of the smoothed curve and the gain the ceiling requires, and the docstring said why: smoothing a gain curve can lift it back above what a sample needed, and one sample over is still over. The control written for it could not make it fire on any signal.

It cannot fire. The running minimum looks over twice the attack window and the smoothing averages over one, so every value the average is taken over is already at or below what the sample in the middle needed. The line is unreachable by construction, and the docstring was describing a danger the construction had already removed.

It stays, because deleting it would leave the property resting on an argument in a comment rather than on a check. What changed is the claim: the test now asserts the property, four attack settings wide, and a second test sets the lookahead to zero and requires the smoothing to lift the curve, so the property is shown to come from the lookahead rather than from luck.

**The reduction was landing 16 frames late.** The required gain per sample comes from the oversampled peak, which is produced by a 257 tap linear phase filter. That filter delays its output by 128 upsampled samples, which is 16 input frames. Nothing removed the delay, so every peak was charged to the frame 16 later than the one it came from, and the gain arrived after the thing it was for.

The measured cost: on a sine at a quarter of the sample rate, where every peak falls between samples, the limiter left the output at -0.90 dBTP against a -1.0 ceiling. It was not meeting the ceiling at all, and the only reason it looked fine on music is that music does not put its peaks between samples that reliably.

With the delay removed, the envelope meets the ceiling to four decimal places on every signal built to break it: the quarter rate sine, a sweep to Nyquist, noise at four times the ceiling, and an isolated click. The constant trim that follows it has never had to act. It stays as a check rather than as a correction, and a test asserts the trim is zero: a trim that is not zero is a report that the envelope missed.

### 32. The residual that came from three other tracks

The low cut declared how far it moves the bands above it: 0.01 percentage points, measured at order 12 across three tracks and written into the module as a constant.

On a file with a lot under 20 Hz it moves them 0.05. The filter removes part of the 20 to 60 band as well, which lowers the total the percentages are taken against, which raises every other band's share. How much depends on how much is down there, which is a property of the file and not of the filter.

The constant is gone. The plan measures the spectrum before and after its own cut and reports what it actually moved on the file in hand. The control compares the number in the plan against a direct measurement of the same file, and a second control requires a cut at 300 Hz to measure differently, so the number is shown to be about the filter that ran.

**A number measured on three files and written into the code is a quoted figure**, however carefully it was measured. It has the same standing as a figure quoted from memory: it describes the files it came from. The standing warning above says no target range is seeded from a quoted figure, and this was the same thing one layer down.

### 33. Three mutants nothing noticed, and no two answers the same

Sixteen mutations were written for the mastering layer, one for each fault already in this file. Three of them survived, and entry 24 says a surviving mutant is a question rather than a verdict. These three had three different answers, and none of them was the answer entry 24 or entry 25 gave.

**The first was a missing control, plainly.** The mutation puts back the call that entry 29 is about: measuring the low cut signal with `loudness.measure` on an `Audio` whose samples have been replaced, so one instrument reads the filtered samples and the other reads the original file. Nothing failed.

I had found that fault by hand, fixed it, and written no test for it. Every other fault in entry 26 got a control while I was writing controls. This one got fixed while I was reading output, and fixing it felt like finishing.

That is the shape worth naming. **A fault found by hand is the one most likely to end up with no control**, because the evidence that convinced you was a number in front of you rather than a test, and once the number moves the work feels done. The controls written deliberately all had controls. The one found by accident did not.

The control now compares the peak the gain was actually derived from against a direct measurement of the filtered signal, on a file with enough under 20 Hz that the filtered and unfiltered peaks differ by far more than the check allows. Its negative control is that difference: if the cut moved the peak by less than the tolerance, the check could not tell which signal had been measured.

**The second was a test that asserted the direction and not the value.** The mutation makes the gain aim at the bottom of the target range whatever the file measures, which is what entry 30 is about. The test written for entry 30 asserted that a file above its range gets a negative gain and a file below it gets a positive one.

Aiming at the bottom of the range also gives a file above the range a negative gain. It gives it a much larger one, all the way across the range instead of just inside the near edge, and the sign is the same either way. The test passed on both behaviours, which means it was never testing the thing entry 30 named.

**A test that asserts the direction of a correction says nothing about where it is aimed.** The assertion is now the value, to 0.002 dB, against the near edge computed from the target and the measurement's own uncertainty. The sign check stays as a second, weaker test, which is fine as long as it is not the only one.

**The third was a test that passed because a different check refused.** The mutation removes the first line of `refuse_unsafe`, which is the one that stops the output folder being the folder the source is in. Two tests cover that line and neither failed.

They could not. With that check gone, the destination becomes the source itself, the source exists, and the next check refuses because the destination already exists. The call still raises, the tests still see the exception they asked for, and the message still contains the folder path because it contains the whole destination path. Every assertion held while the safeguard they were written for was gone.

This one matters more than the other two, because the check it covers is the one that stops the tool writing over somebody's master. It was the only mutant of the sixteen that could have destroyed a file, and it was the one the suite was blindest to.

**A test that asserts only that something was refused cannot tell you which check refused it.** Both tests now assert the reason. The folder refusal has to name the folder as the problem, the existing file refusal has to name the file, and each asserts the other's words are absent. That last part is what makes them distinguishable rather than merely worded differently.

There is a second lesson underneath. Two safeguards that overlap look like defence in depth and behave like one safeguard with a spare. Entry 26 records deleting a third branch of this same function because it could not be reached. What this mutant shows is that unreachable was the wrong word: the branch was reachable, the check above it just got there first, and the same is true in the other direction. Overlap is not redundancy unless the tests can tell which one is holding.

All three passed a green suite, and all three were written the same day as the code they cover.

### 34. The objective whose best answer is to do nothing

Every limiter setting the search picked on a nine track record came back on the edge of the grid it was picked from. A grid whose answer is always its own boundary is reporting the boundary, so the grid was widened: four attacks became six, spanning 0.1 to 30 ms, and three releases became six, spanning 3 to 1000 ms.

The winners still came back on the edges. Collateral took 0.1 ms and 100 ms, which is one edge and one interior. Acquisition took 0.1 and 1000, both edges at the extremes. Settled took 30 and 1000, both edges at the other extreme. So the attack is not simply always the fastest: two files took the shortest offered and one took the longest.

The whole surface, measured on Settled, is what explains it. Band movement in percentage points, `x` where the setting changed a verdict against the target:

```
attack\release      3       10       30      100      300     1000
         0.1     0.51     0.52     0.56     0.59     0.54     0.29
         0.3     0.53     0.52     0.56        x     0.54     0.29
           1     0.59     0.57     0.60        x     0.56     0.30
           3     0.57     0.60        x        x     0.61     0.29
          10        x        x        x        x     0.61     0.27
          30        x        x        x        x     0.62     0.26
```

Two things are in that table. The release decides almost everything: every column under 1000 ms sits near 0.55 and the 1000 ms column sits near 0.28. The attack decides almost nothing: down that last column, six settings spanning a factor of three hundred move the balance by 0.04 in total, which is eight of the 0.005 steps a percentage is reported in. The attack's real effect is on which settings are allowed at all, not on which is best.

**The reason the release always wins at the maximum is that the objective is degenerate.** The search keeps every setting whose output leaves every band's verdict where it was, and among those it takes the one that moved the balance least. A limiter with an infinitely long release never lets the gain back up, which is a constant gain, and a constant gain moves no band at all. So "moves the balance least" is minimised by the setting that does the least limiting, and its true optimum is not to limit. Bounded by a grid that looks like a choice. Unbounded, its answer is a static gain cut, which is not an answer to the question being asked.

Widening the release further would move the winner to whatever new maximum it was given, for as long as anyone kept widening it.

**What was tried and did not ship.** The obvious repair is to make the objective the thing actually wanted, the most loudness reached, and leave the verdicts as the constraint that stops it being reached by damage. That is well posed and its optimum is interior. On the one file where the target is reachable and the outcome could be checked, it landed 0.048 LU short of the target where the old objective landed inside. The reason is that the loudness a setting reaches before the gain correction is not the loudness it reaches after: the correction lifts the gain until the measurement clears the floor, and the setting that starts loudest can be the one with least room left before a verdict changes. Measuring the loudness after correction would mean running the correction loop for every setting in the grid, which is thirty six times the work.

So it stays as it was, on one file's evidence against it, which is exactly the standard entry 30 was written about. The change is not being made on one file's evidence for it either.

**What ships.** The wider grid, because the release genuinely spans it, and the plan now reports the spread the winner was chosen out of. A choice made across 0.04 points and a choice made across half a point read identically when only the winner is printed, and they are not the same kind of choice.

The lesson is about objectives rather than controls. Entry 27 was a criterion no setting could fail, which chose nothing and said so loudly. This is quieter: a criterion every setting can fail, ranked by a quantity whose best value is at a setting nobody would want. **A grid can hide a degenerate objective by never offering it what it really wants.**

### 35. A fix that made one rule conditional on another

Entry 30 records a gain that turned down files already inside their target: it computed the distance to the bottom of the range whatever the file measured, so a track sitting in the middle would have been pulled to the edge of it. The fix refused the gain when the loudness was already inside.

The refusal returned before the ceiling had been looked at.

`Crown me now.wav` measures -9.497 LUFS, inside boom bap's -9.734 to -8.434, and -0.3 dBTP against a -1.0 ceiling. The run applied nothing at all. A file 0.7 dB over the ceiling came back untouched, and the report said the loudness was fine, which it was.

The two rules are not connected. The target range is a statement about loudness. The ceiling is a delivery limit on the peak, and a file over it comes under it whether or not it wants loudness. What entry 30 established is only that the loudness should not be moved, and the way to say that is to aim the loudness at where it already is rather than to stop planning.

So the aim is now the measured loudness when the file is inside its range, and the ceiling clamps the gain as it does for every other file. On that track it takes 0.95 dB off, bound by the ceiling, which puts the peak at -1.25 dBTP and the loudness at -10.45, out of the bottom of the range by 0.7. That is a real conflict rather than a hidden one: the shortfall is reported and the limiter is asked to recover it, which is the same path a file that is too quiet takes.

The gain is refused now only when neither rule asks for anything, and it says both: this loudness is inside that range and this peak is under that ceiling.

**A fix that stops one thing happening by returning early stops everything after it happening too.** The refusal in entry 30 was correct about the gain and silently authoritative about the ceiling, the limiter and the prediction, none of which it had been asked about. The narrower form, which is the one that survives, changes the aim rather than the control flow.

Two tests hold it. A file inside its loudness range and over the ceiling gets a negative gain bound by the ceiling, and the control beside it asserts that the file really is inside its range, because if it were outside on loudness too the gain would have been asked for by the loudness and the ceiling would prove nothing. A third runs it end to end and requires the written file to be inside the ceiling.

There is a shape here worth carrying. Every one of the six faults in entry 26 and the three in entry 33 was found by measuring. This one was found by someone opening the page and reading a plan that had nothing in it. **A report that says what it did not do, and why, is what made it findable at all**: the plan named its own refusal in the words of the rule that refused, and the words were about loudness while the number on screen was a peak.

## Standing warning: where target numbers come from

Measurements taken before 2026-08-26 in other sessions were mostly made with
librosa at its default `sr=22050`, which discards everything above 11 kHz, and at
`mono=True` discards the stereo field. Any figure quoted from those sessions
about the 8k to 16k band or about stereo width is suspect and cannot be used.

So: **no target range in `targets/` is seeded from a quoted figure.** Every range
is re-measured by this bench from the reference file at its native rate, and
`evidence.n` on the profile says how many files it came from, so a range built
from two references cannot be mistaken for a law.

The same discipline applies to lossy references, and for the guaracha profile it
has to, because both references are mp3. A lossy file is a reliable source for
some fields and not for others, and the profile must say which:

- Loudness and the low and mid balance survive encoding well enough to use.
- True peak does not. `Bam Bam` decodes to +1.1 dBTP, which is the codec
  overshooting a master that was limited near zero, not the master's own peak.
- Anything above the encoder's lowpass does not exist. `Bam Bam` holds 0.04
  percent in the 16 to 20 kHz band, so the encoder cut it around 16 kHz and the
  air bands cannot be seeded from it at all.

Each profile therefore records the source format per field, the same way it
records `evidence.n`. A field seeded from a lossy source is marked as such, and a
field that a lossy source cannot support is absent rather than filled in.

### 36. A value the server filled in, sitting beside a control that had moved

The control bar carried an OUTPUT field: the folder a master would be written into,
worked out from the selection and shown before the button was pressed. It was correct
every time the server drew it.

The page opened on `Currency of Souls/` and the field read `Currency of Souls
(Mastered)/`. Choosing `Pull me under/` in the picker left it reading `Currency of
Souls (Mastered)/`, because nothing had been submitted and the server had not drawn
the page again. Asked for that selection directly, it answers `Pull me under
(Mastered)/`. The value was never wrong. It was answering a question nobody was
asking any more.

The page carries no script by design, so a field the server fills cannot follow a
select. Everything else in the bar is a control the browser keeps in step on its own,
and the one item that was not read as though it did.

The field is gone. Where a run writes is named on the mastering card from the moment
the run starts, which is a statement about a run that exists rather than a prediction
about a selection that may already have changed, and `./` is still refused with a
reason.

**A read-only value placed among controls inherits their promise to be current.** The
fault was not in the value or in the rule that produced it. It was in putting it where
the page implies it tracks what is on screen.

The control asserts the bar holds no rendered text at all, so any value placed back
among the fields fails it. This one was found by someone reading the page, which is
the second in a row: entry 35 was found the same way, and both were in what the page
said rather than in what it measured.

### 37. A test fixture living in the folder the shipped targets live in

The mutation tool checks the suite is green before it mutates anything. It reported
`test_every_shipped_target_says_what_it_rests_on` failing on a target the repository
does not hold.

The `album` fixture in the serving tests writes a small target and deletes it
afterwards, and it was writing it into `targets/`, beside `boom-bap.json` and
`guaracha-club.json`. A serving run was going while the mutation tool copied the
repository, so the copy caught the fixture's file mid-life and read it as shipped. It
has `evidence.n` of 1 and no sources, which is exactly what the test refuses, and the
test was right to refuse it.

The two ways this shows up are the same fault. A second run alongside the first sees
it, and a run that is killed before teardown leaves it there for the next one. Either
way something the bench does not ship is sitting where everything reads targets from.

The fixture now writes into a folder of its own and points `serve.TARGETS` at it, so
there is nothing to clean up and nothing to leak. The teardown that deleted the file
is gone with it.

**A test that writes into a folder the program reads as authoritative is not isolated,
however carefully it tidies up.** Tidying up runs last, and the two cases that matter
are the ones where something else reads first or nothing runs last.

Nothing here says a shipped target was ever wrong. The check held, which is why this
was visible at all, and the file it caught was never one of the two.

### 38. The fixture that never entered the loop it was named for

A full run of the mutation tool came back with two survivors, both in the loudness
correction loop inside `search_limiter`: setting `CORRECTION_PASSES` to 0, which
deletes the loop, and dropping the clearance out of the aim, which lands the loop on
the boundary it was derived from. Nothing in 338 tests noticed either.

Reading the `mastered` fixture back said why in one line:

```
correction_db      0.0
corrected_from     absent
cleared_the_floor  True
accepted / tried   36 / 36
```

The chosen limiter setting cleared the floor on the gain arithmetic alone, so the
loop was never entered. The first mutant deletes code that does not run. The second
edits an expression that is never evaluated.

Two tests were written against that fixture. `test_the_loudness_lands_inside_the_target`
passes because the gain got there without the loop.
`test_the_correction_stops_with_room_and_not_on_the_condition` asserts
`cleared_the_floor` and then a margin, and both hold with no correction at all. Its
own docstring said "this file is built so the correction can reach its aim". The file
never needed the aim.

Both mutants exist because of entry 26, which found and fixed those two faults. The
fixes are real and still in the code. What was never built was material that reaches
them, so for as long as the guards have existed they have been guarding nothing.

The fixture that reaches the loop was found by sweeping rather than assumed. Source
saturation and target push were varied and the run read back off each combination.
Three things have to hold together: the loop is entered, it reaches its aim, and the
output lands inside the target. At the shipped `drive` of 4.0 they do not. A push of
1.0 LU, which is what `mastered` uses, never enters the loop at all. A push of 1.5
enters it by 0.006 dB and clears, but the file does not arrive. Pushes from 2.0 to 8.0
enter it and never clear, and before entry 39 bounded it, 6.0 and above ran the
correction away to 169 and 301 dB.

At `drive` 2.0 with a push of 1.5 LU all three hold: `correction_db` 0.098,
`cleared_the_floor` true, arrived. Less saturation leaves the limiter loudness to
give back, which is the condition the loop exists for.

A control was written before anything else. `test_that_file_really_needs_the_correction`
asserts `correction_db` is above zero, so a fixture that stops reaching the loop fails
there rather than passing everywhere. It catches the deleted loop and it does not
catch the changed aim, which is right: with the aim moved the loop still runs. A
control that caught both would be a third copy of the other two.

```
predict the loudness instead of measuring it              caught by 3
stop the correction on the condition it was derived from   caught by 2
```

**A test names the code it is about. Only its fixture decides whether it reaches it.**
The name, the docstring and the assertions were all about a loop the material never
provoked, and every one of them read as coverage.

The fault was invisible for the same reason it existed. No test drove the code, so
nothing could report on the code being undriven. Only an instrument that breaks the
code and asks whether anything notices can see a guard that has never been armed.

Nothing here says the correction loop is wrong. On real material it runs: `Settled.wav`
against boom bap corrects by 1.36 dB. It was exercised in use and not once in the
suite.

### 39. A clamp on the divisor, read as a bound on the result

Entry 38's sweep turned up a second thing. Asked for 6 LU more than it had, the
loudness correction planned a gain of 169 dB. At 8 LU it planned 301.

```
pass 1: short 4.009  raw slope 1.00000  clamped 1.000  lift  4.009  total   4.009
pass 2: short 3.611  raw slope 0.09927  clamped 0.099  lift 36.375  total  40.384
pass 3: short 3.230  raw slope 0.01929  clamped 0.050  lift 64.602  total 104.986
pass 4: short 3.226  raw slope 0.00746  clamped 0.050  lift 64.522  total 169.508
```

Pass 3 buys four thousandths of a LU for 64 dB.

`SLOPE_LIMITS` has a floor, and its comment says "The floor stops the correction asking
for a gain that no setting could survive". It stops nothing. It clamps the divisor,
which caps the multiplier at twenty and lets it compound across passes. The comment
described a property the code did not have, and reading the comment is how the loop
kept looking sound.

Underneath that is the reason no clamp on a divisor could have helped. A limiter's
loudness per dB of gain only falls. A step read off the slope measured so far is a
linear extrapolation of a decaying function, so it always overshoots, and the further
into saturation the worse. The fault is in the size of the step, not in the number it
is divided by.

Nothing rejected the result either. A candidate is accepted when it changes no band's
verdict and puts no sample over full scale. At plus 169 dB the limiter is a constant
gain, and a constant gain moves no band at all, so the runaway passed the criterion
for the same reason entry 34 records: the objective's best answer is to do nothing
dynamic. The degeneracy that makes the search weak is what made the runaway invisible
to it.

The bound that stayed is one line and rests on a number the run already has: the
correction may not exceed the gain the plan asked for. A correction larger than the
thing it corrects is not a correction, it is a second plan. What it costs when the
target really is out of reach is a run reporting that it did not clear the floor and
did not arrive, and why, which this bench already knows how to say. The 169 dB was the
loop refusing to give that answer.

Two other bounds were written at the same time and removed before the commit: a step
no larger than the gain already measured over, and a stop when the slope reaches its
own floor. Both are defensible in isolation, and no test caught either mutant. They
are not untested, they are unreachable. Once the correction cannot exceed the plan's
gain, a step bound only changes how many passes it takes to reach that cap and the
slope stop can only fire before the cap when the lifts are small, which is when the
ordinary stop condition fires first. Taking both out changed no figure in the
verification: 169.508 to 6.055, 301.367 to 8.055, and the two converging fixtures
untouched at 0.098 and 0.0. That is entry 38's lesson one file over, and it is easier
to make than to notice.

**A clamp on a divisor is not a bound on the result.** Neither is a comment saying it
is one.

It never fired on anything mastered here. All eleven masters on disk plus one made
during the audit were measured against their sources: loudness lifted 3.2 to 5.3 LU,
crest given up between 0.33 and 2.83 dB, every one landing on the ceiling less its
clearance. The smallest crest any of them came out with is 9.79 dB, where a runaway
would have flattened a file toward nothing. The two runs that fell short of their
target, which is the condition the runaway needs, lost 1.64 and 1.71 dB and stopped on
their own.

### The quoted figure that the measurement contradicted

The boom bap profile was asked for on a stated premise: that the style carries a
much heavier 60 to 250 band than guaracha. That figure was quoted, not measured.

Measured across three references it runs 18.37 to 36.22 percent. Guaracha, from
two, runs 23.64 to 35.93. Not heavier. Overlapping almost exactly, and the
lightest single value across both sets belongs to the boom bap side.

This is the rule above doing the only useful thing a rule like it can do. Had the
premise been seeded, the profile would have carried a bound nothing measured
supports, and every track checked against it would have been judged against a
number that came from memory. The premise is recorded in the profile's evidence
block next to the measurement that contradicts it, because a profile that
silently disagrees with the reason it was built teaches nobody anything.

One reference was dropped from that set, and dropping it is recorded too. `SICKO
MODE` is a bootleg re-edit rather than a released master, minus 4.8 LUFS against
minus 8.4 to minus 9.7 for the other three, with 63732 clipped runs and 627823
samples over full scale. **Removing a reference to tighten a bound is choosing
the evidence, so the profile names what was removed and why.** The distinction
that makes it legitimate here is that the file is not what it claims to be, which
is a fact about the source rather than a preference about the answer.

### Where the guaracha references went

`tools/seed_target.py` can no longer rebuild the guaracha profile. Both mp3s were
on the machine when it was seeded and are not there now. The committed
`targets/guaracha-club.json` is the only record of those measurements, which is
why the profile stores the filename, container, codec and measured rate of every
source alongside the numbers.

The seeder skips a profile whose references are gone rather than failing, and
says so, because the alternative found here was that one missing profile stopped
a second one from being written at all.

## Carried over, still binding

- **A measurement that is blind exactly where it matters is worse than none.** On
  the previous project a drift readout fitted phase in chunks, phase wraps at half
  a beat, and the readout went silent on precisely the tracks that walk. It had a
  test, so the test was wrong too. Tempo drift here declares its horizon or it
  does not ship. If the horizon turns out to sit inside the tracks it is for, it
  gets deleted rather than kept as a number that goes quiet when it matters.
- **A unit test written after the code, by reading the code, passes on the wrong
  answer.** When a test and a measurement of real material disagree, the test is
  the one written by whoever wrote the bug.
- **An instrument that cannot see something should say so**, rather than picking.
- **Bump the cache version with any change to what a number means.** Otherwise the
  cache serves yesterday's answer with today's confidence. Cache keys here are
  file sha1 plus engine version for exactly this reason.
- **The tempo octave must not be a question about mix balance.** Measured on the
  previous project: taking the doubling ratio on summed spectral flux let a 2 dB
  shelf move the reported tempo by an octave on real files. Taking it on an
  envelope where each of eight log spaced bands is divided by its own mean before
  summing is exactly invariant to any static per band gain, and moved 0 of 26
  files under a 2 dB shelf against 2 of 26 for the old estimator. `tempo.py` uses
  the normalised envelope, and the shelf invariance is a control it must pass
  before its output is believed.

## Predicted, not yet observed

These have not bitten in this repo. They are written down before the fact so that
when one of them does, the entry moves up into "Observed here" with what it
actually did. Nothing below is a claim of experience.

**The onset refit in the drift model stays until it can be shown to fail.** Entry 25
found that it does not shape the drift curve: the curve is the windowed estimate, and
over the same interval the two agree to 0.036 BPM on the known answer set and 0.013 on
real material. That is a reason to stop describing it as the mechanism, which the
registry now does not. It is not yet a reason to delete it, because the case that would
settle it has not appeared: material where the windowed estimate genuinely fails.

The condition for removal, set deliberately rather than left to judgement: find a file
where the short window trajectory is wrong, then show the onset refit does not rescue
it. Both halves are required. Until then the code stays, described accurately, doing
something small.

The reason for the condition is not the code. Three conclusions about this one function
were drawn today and two were wrong, both from comparisons where more than the studied
thing had changed. A structural deletion argued for by the same method that produced
those two is not worth making yet.

1. **Gated and ungated are different animals.** Integrated LUFS is gated at -70
   absolute and -10 relative. A crest factor taken against ungated RMS quietly
   rewards long silences. Control: appending 30 s of silence must not move crest.
2. **Band percentages sum to 100 by construction.** Asserting that they sum to 100
   is the self agreeing check in its purest form. The control is two tones of
   known amplitude in known bands, asserting the split analytically, plus a
   Parseval check against time domain energy.
3. **The denominator must not run to Nyquist.** If it does, the same master at
   44.1k and 48k reports different band percentages and nothing says why. Fixed at
   20 Hz to 20 kHz, with energy outside that reported separately rather than
   silently dropped.
4. **Clipping counted per sample flags peak normalised material as damaged.** Runs
   of three or more consecutive full scale samples, threshold stated. Control in
   both directions: a file normalised to exactly 1.0 must read zero runs, and a
   genuinely squared off file must read more than zero.
5. **Correlation on near silent frames is noise over noise.** Gate the frames and
   report how many were excluded, or a quiet intro sets the width of the track.
6. **DC offset over a file with a fade is the mean of a nonstationary signal.**
   Per channel mean and the maximum block mean, so a DC step does not average out.
7. **Grid fit confidence has no defensible scale.** There is no 0 to 1 field. The
   residual is reported as a median absolute deviation in ms with the count of
   onsets that fitted, or there is no field.

The default sample rate trap that used to head this list has moved: it is guarded
by the rate comparison in `decode.py` and by four mutations in `tools/mutate.py`,
and it is the reason for the standing warning above.

## What the suite proves, and how that is checked

`tools/mutate.py` breaks the engine one way at a time and reports which tests
caught each break. It works on a copy of the tree, never the tree itself, for the
reason in entry 14. Run 2026-08-27, 101 tests in the baseline:

```
mutation                                                caught by
resample to 22050, report 22050                         42 tests
resample to 22050, report the source rate               41 tests
drop the last tenth of the file                         39 tests
downmix to mono                                         35 tests
truncate to a fast length instead of padding up to one  19 tests
run the denominator to Nyquist                           4 tests
measure loudness without the K weighting                 3 tests
read the metadata true peak as decibels                  3 tests
drop the relative gate                                   2 tests
leave out the one sided doubling                         2 tests
true peak with scipy's default filter                    1 test
report momentary loudness as integrated                  1 test
report the -70 floor as a measurement                    1 test
assign whole bins by the band their centre is in         1 test
double every bin, direct current and Nyquist included    1 test
take crest against an ungated root mean square           1 test
count samples at full scale instead of runs              1 test
put full scale at 1.0 whatever the bit depth             1 test
correlate the channels without removing their means      1 test
delete the duration cross check                          1 test
```

That table is the exhaustive run, which puts every mutant through the whole suite.
The twenty mutations it lists were the engine as it stood then. The mastering
layer added sixteen more on 2026-08-28, checked in stop early mode, where a
mutant runs only until the first test that catches it. That answers whether a
break is noticed and not how many tests notice it, so they are not in the table.
Two of them survived the first pass and entry 33 is what each one turned out to
mean.

The counts at the top are inflated and should not be read as reassurance. Almost
every test decodes a file, so anything that breaks decoding breaks most of the
suite. That is a measure of coupling, not of coverage. The bottom of the table is
the part that carries information. Ten rows are held by a single test each, and
these six are the ones whose absence would be hardest to notice:

- `test_container_duration_disagreeing_with_frames_is_caught` is all that stands
  between the bench and a silently missing duration cross check.
- `test_true_peak_finds_the_intersample_peak` is all that separates the designed
  oversampling filter from scipy's default. That difference is 0.015 dB, under
  ffmpeg's print resolution, so no cross check between the two loudness
  instruments can see it and only the analytic control can.
- `test_the_two_instruments_agree_within_the_stated_tolerances` is all that catches
  momentary loudness being reported as integrated. The two are identical on
  constant material, which is most of what a synthetic suite contains.
- `test_silence_has_no_loudness_and_no_peak` is all that keeps the -70 floor from
  being printed as a measurement.
- `test_band_power_weights_partial_bins` is all that holds the band edge weighting
  in place. Nothing measured from a real file can see it, per entry 11.
- `test_parseval_holds_with_direct_current_and_nyquist_content` is all that checks
  the one sided doubling at the two ends of the spectrum, and it only works
  because its signal is built out of the components the fault acts on.

Some tests in that table earn their place by refusing to pass rather than by
passing. `test_decode_keeps_content_above_11k_can_fail` puts a signal resampled to
22050 through the same assertion and requires it to be rejected.
`test_container_duration_check_can_fail` requires the duration tripwire to hold its
fire on a correct file, because a tripwire that fires on everything catches
nothing. `test_loudness_of_a_tone_can_fail` requires the unweighted loudness of the
same tone to be refused at the same tolerance, which is what makes the K weighting
control a control.

`test_summing_to_one_hundred_proves_nothing` is the sharpest of them. It runs the
sum check on a band set of nonsense edges, 20 to 21 Hz, 21 to 22 Hz and so on, and
the sum comes to 100. Then it puts the same band set through the analytic split
check, which refuses it. The check that cannot fail and the check that can are set
side by side in one test, so nobody has to take the distinction on trust.

One thing the mutation table cannot show: both loudness instruments implement the
same recommendation, so a misreading of the recommendation itself would appear in
both and the deltas would stay at zero. Agreement between them is evidence about
implementation, not about correctness. That is what the analytic controls are for,
and it is why the K weighting is checked against the published coefficient table
and the tone loudness against the filter's frequency response rather than against
the other instrument.

Neither the suite nor the mutation tool is proof. `tools/mutate.py` only tests the
mutations somebody thought to write, which is the same limit every check in this
file has. When a number turns out to be wrong, the entry goes in "Observed here"
with what it said, what was true, what caught it and what changed.
