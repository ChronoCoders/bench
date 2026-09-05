"""What each number is and how it would lie. One entry per method id.

This file is where that prose lives. It does not belong in the modules as well.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Method:
    id: str
    measures: str
    computed_from: str
    failure_modes: tuple[str, ...]
    cross_check: str
    controls: tuple[str, ...]


_METHODS = (
    Method(
        id="probe/ffprobe",
        measures="container, codec, sample rate, channel count, bit depth, claimed duration",
        computed_from="ffprobe on the first audio stream. Container metadata only, nothing is decoded.",
        failure_modes=(
            "Every field here is a claim the file makes about itself, not a measurement of the samples. "
            "An mp3 with no Xing header reports a duration derived from bitrate that can be wrong by seconds.",
            "bits_per_sample reads 0 for lossy codecs. Reported as 0 it would look like a measured zero, "
            "so the field is absent instead.",
            "format_name is a comma separated list for the mp4 family. Taking the first token names the "
            "wrong container, so the whole string is kept.",
        ),
        cross_check="Frames actually decoded divided by the decoded rate, against the duration the container "
        "claims. The two come from different places, and a claim that is wrong moves only one of them.",
        controls=(
            "test_probe_reads_wav_pcm_fields",
            "test_probe_omits_bit_depth_for_lossy",
            "test_container_duration_disagreeing_with_frames_is_caught",
            "test_container_duration_check_can_fail",
        ),
    ),
    Method(
        id="decode/native-rate",
        measures="sample values, at the rate and channel count the file was written with",
        computed_from="soundfile where libsndfile can read the format, otherwise ffmpeg to pcm_f64le at the "
        "rate and channel count ffprobe reported. Nothing in this path resamples or downmixes.",
        failure_modes=(
            "A loader with a default sample rate returns 22050 Hz. Everything above 11 kHz reads zero, every "
            "check downstream still agrees with itself, and no field in the output says the content was "
            "thrown away. librosa.load does exactly this unless told sr=None.",
            "A loader with a default mono downmix returns one channel. Correlation then reads exactly 1.0 and "
            "side energy exactly zero, which are both legitimate values for a real mono master, so the "
            "output looks measured rather than destroyed.",
            "An ffmpeg fallback invoked without an explicit rate can pick its own.",
            "float32 output truncates 32 bit integer PCM. pcm_f64le does not.",
            "The duration cross check is blind to a resample on its own: n/2 frames at r/2 Hz is the same "
            "number of seconds, so only the rate comparison catches a loader that resamples and reports "
            "the rate it produced. This text used to claim otherwise. See entry 1 of measuring.md.",
        ),
        cross_check="Two checks that do not overlap. First, the rate the decoder reports against the rate "
        "ffprobe read from the container: different sources, so a loader with its own default rate "
        "disagrees with the file. Second, decoded frames divided by the decoded rate against the "
        "container duration, which catches a truncated decode and a decoder that resampled while still "
        "claiming the source rate.",
        controls=(
            "test_decode_keeps_content_above_11k",
            "test_decode_keeps_content_above_11k_can_fail",
            "test_decode_keeps_both_channels",
            "test_decode_keeps_both_channels_can_fail",
            "test_decode_refuses_a_rate_that_is_not_the_source_rate",
            "test_decode_pcm16_round_trips_exactly",
            "test_decode_pcm24_round_trips_exactly",
            "test_ffmpeg_and_soundfile_decode_the_same_samples",
        ),
    ),
    Method(
        id="loudness/ffmpeg-ebur128",
        measures="integrated loudness, loudness range, true peak, sample peak",
        computed_from="one ffmpeg run of the ebur128 filter with metadata and peak reporting on. "
        "Loudness comes from the frame metadata at three decimals and is checked against the "
        "Summary; the peaks come from the Summary in decibels and are checked against the metadata.",
        failure_modes=(
            "The Summary prints one decimal place. Reading loudness off it caps every figure at "
            "0.1 LU, which is why the loudness values are taken from the frame metadata instead.",
            "The metadata peaks are linear amplitude, not decibels, and they land in a range where "
            "a decibel figure looks plausible. A file peaking at 2.9 dBTP publishes "
            "true_peak=1.401, and reading that as decibels is wrong by 1.5 dB with nothing in the "
            "output to suggest it.",
            "Those linear peaks are printed to three decimals, so they cannot represent anything "
            "below about -66 dBFS and print 0.000 there. Treating that zero as silence throws away "
            "a peak the Summary reports perfectly well.",
            "The filter prints running momentary figures throughout the run. Parsing the first "
            "match rather than the Summary reports momentary loudness as integrated.",
            "An integrated reading of exactly -70.0 is the absolute gate itself, the filter's "
            "floor, not a measurement. A genuine gated loudness of exactly -70.000 would be "
            "reported as absent by this bench, which is the price of not reporting a floor as a "
            "figure.",
            "True peak of digital silence prints as -inf, which is a float and will propagate "
            "through arithmetic without complaint.",
        ),
        cross_check="bs1770.py, an independent implementation of the same recommendation, on every "
        "file. The deltas are reported in the measurement rather than averaged away.",
        controls=(
            "test_metadata_peaks_are_linear_not_decibels",
            "test_a_second_summary_block_is_refused",
            "test_silence_has_no_loudness_and_no_peak",
            "test_shorter_than_a_gating_block_has_no_integrated_loudness",
            "test_shorter_than_a_short_term_window_has_no_loudness_range",
            "test_true_peak_finds_the_intersample_peak",
            "test_true_peak_can_fail",
            "test_the_primary_instrument_meets_the_published_value",
            "test_the_loudness_tolerance_can_reject",
            "test_the_true_peak_tolerance_can_reject",
        ),
    ),
    Method(
        id="loudness/bs1770-4-numpy",
        measures="the same four figures, independently",
        computed_from="ITU-R BS.1770-4 and EBU Tech 3342, implemented in numpy from the "
        "recommendations. K weighting coefficients are derived at the file's own rate from the "
        "analog prototype rather than being the 48 kHz table reused everywhere.",
        failure_modes=(
            "It could be tuned to agree with ffmpeg. If that ever happens the bench has one "
            "instrument wearing two names and every cross check involving it becomes decoration.",
            "Hard coding the published 48 kHz coefficients and using them at 44.1 kHz shifts the "
            "shelf by about 9 percent. The control is that the derivation reproduces the published "
            "table at 48 kHz to 1e-13.",
            "The gates are strictly greater than. Using greater or equal changes the answer on "
            "material sitting exactly at a gate, and the two gates are separate mechanisms: one "
            "can be deleted while a test aimed at the other stays green.",
            "EBU Tech 3342 does not pin down how the percentiles are taken. A histogram and a "
            "linearly interpolated percentile give slightly different loudness ranges, so exact "
            "agreement with any other implementation is not expected and not required.",
            "The oversampling filter for true peak decides the answer. scipy's default "
            "resample_poly filter overshoots the analytic control by 0.015 dB; the 257 tap Kaiser "
            "used here reads it to within 0.0005 dB.",
            "Its length cannot be traded for speed on the strength of the analytic control alone. "
            "A 129 tap version reads that control identically and still parts company with 257 "
            "taps by 0.029 dB on a real master, which is nothing against the 0.15 dB agreement "
            "tolerance and enough to flip a -1 dBTP ceiling. The disagreement is largest on the "
            "files closest to full scale, so the instrument is least certain exactly where the "
            "question is asked. See entry 13 of measuring.md.",
        ),
        cross_check="Two analytic answers that involve neither instrument: the loudness of a tone "
        "computed from the filter's frequency response, and the true peak of a sine sampled either "
        "side of every peak, which is 3.01 dB above its own sample peak.",
        controls=(
            "test_kweighting_matches_the_published_48k_table",
            "test_kweighting_table_check_can_fail",
            "test_loudness_of_a_tone_matches_the_filter_response",
            "test_loudness_of_a_tone_can_fail",
            "test_material_below_the_absolute_gate_is_excluded",
            "test_material_below_the_relative_gate_is_excluded",
            "test_the_gates_can_fail",
            "test_lra_of_two_levels_is_their_separation",
            "test_lra_of_a_constant_level_is_zero",
            "test_lra_can_fail",
            "test_the_second_instrument_meets_the_published_value",
            "test_the_loudness_tolerance_can_reject",
            "test_the_true_peak_tolerance_can_reject",
        ),
    ),
    Method(
        id="loudness/two-instruments",
        measures="the difference between the two, per figure",
        computed_from="both instruments on the same decoded samples, subtracted. Nothing is "
        "averaged and no figure is dropped in favour of the other.",
        failure_modes=(
            "The uncertainty reported for each field is the largest of three things: half the "
            "last digit the primary instrument prints, the gap between the two instruments, "
            "and for true peak a further 0.03 dB, which is how far the 129 and 257 tap "
            "oversampling filters disagreed on real masters. True peak is printed to one "
            "decimal, so its uncertainty never falls below 0.05 dB. Anything comparing this "
            "number to a ceiling and ignoring that will pass a file sitting inside the error "
            "bar.",
            "Averaging the two would turn a right answer and a wrong one into a wrong answer with "
            "the evidence discarded. The deltas are reported instead.",
            "The tolerances could drift into targets. They were measured, they are printed with "
            "the result, and a delta beyond one of them is listed rather than absorbed.",
            "Two of them are set by how ffmpeg prints rather than by any disagreement about the "
            "audio. The peaks are read from a Summary that quantises to 0.1 dB, so 0.06 dB of "
            "each peak tolerance is that and nothing else. The true peak tolerance of 0.15 dB is "
            "0.06 of printing plus 0.09 of genuine difference between two interpolators of "
            "different lengths. On bandlimited material the two agree to within 0.08 dB.",
            "A true peak flag usually means the file has a hard discontinuity, a start or end mid "
            "waveform or a hard edit, rather than that either instrument is faulty. Reading every "
            "flag as a fault would train the reader to ignore them.",
            "Agreement is not correctness. Both implementations follow the same recommendation, so "
            "a misreading of the recommendation itself would show up in both and the deltas would "
            "stay at zero. That is what the analytic controls are for.",
        ),
        cross_check="Neither instrument checks this one. The analytic controls do, and so does the "
        "discontinuity case, which is the only material here that makes the flag fire.",
        controls=(
            "test_the_two_instruments_agree_within_the_stated_tolerances",
            "test_a_discontinuity_makes_them_disagree_about_true_peak",
            "test_gain_change_moves_both_instruments_by_the_same_decibels",
            "test_gain_change_does_not_move_loudness_range",
        ),
    ),
    Method(
        id="spectral/periodogram-band-energy",
        measures="energy per band as a percentage of energy between 20 Hz and 20 kHz",
        computed_from="one real transform over the whole file per channel, zero padded up to a "
        "fast length so no audio is dropped, power summed across channels with the one sided "
        "doubling applied. Each bin is weighted by how much of it lies inside the band.",
        failure_modes=(
            "The percentages sum to 100 by construction and that sum is not evidence. It holds "
            "with the right band edges, with wrong ones, and with nonsense ones, because the last "
            "step divides by the sum of the others.",
            "This figure has no independent second instrument at runtime. That is a limit, not an "
            "oversight: by Parseval the whole file transform is the exact energy of the file per "
            "band, so any other method measures the signal through a response that is not ideal "
            "and answers a slightly different question. Welch and an elliptic filterbank were "
            "both built and both landed about 0.9 points away on real music, in a direction set "
            "by where the music sits relative to a band edge. See entries 9 and 10 of "
            "measuring.md.",
            "The transform describes the periodic extension of the file, so a file that starts "
            "and ends mid waveform carries the energy of that discontinuity. On a faded master it "
            "is 0.0001 points. On an excerpt chopped out of a longer track it is not, and nothing "
            "in the output says so.",
            "A denominator running to Nyquist would make the same master report different "
            "percentages at 44.1 kHz and at 48 kHz, with nothing in the record to say why. It is "
            "fixed at 20 Hz to 20 kHz and energy outside is reported rather than dropped.",
            "Below a 40 kHz sample rate the band set cannot be measured as specified. The bands "
            "above Nyquist are absent, the denominator shrinks, and `complete` is false. "
            "Percentages from an incomplete band set are not comparable with a target.",
            "The one sided doubling applies to every bin except direct current and, at an even "
            "length, Nyquist. Doubling those two as well inflates the ends of the spectrum, and "
            "nothing about the percentages looks wrong when it happens. Test material without "
            "direct current or Nyquist content cannot see it at all, which is why one control "
            "signal is built mostly out of both.",
            "Weighting each bin by its overlap with the band decides the answer, but at a bin "
            "width of five thousandths of a hertz it is worth less than a thousandth of a point, "
            "so no measurement of a real file can tell it from assigning whole bins. It is "
            "checked directly on a synthetic spectrum with 7 Hz bins instead, where the two "
            "answers are 40 and 42.",
            "Below one second a bin is wider than a hertz and the 20 Hz edge stops meaning "
            "anything. There is no spectral measurement there rather than a coarser one.",
        ),
        cross_check="No second instrument, by the argument above. What stands in its place is "
        "three analytic controls whose answers are known before the file or the code exists: two "
        "tones whose split follows from their amplitudes, a flat spectrum whose bands follow from "
        "their widths, and Parseval against the sum of squares of the samples. Then a per band "
        "round trip through the inverse transform, which checks the band arithmetic and the one "
        "sided doubling by a route that ends in the time domain. Then an elliptic filterbank, on "
        "controlled signals only, where nothing sits near a band edge and its soft skirts cannot "
        "bite.",
        controls=(
            "test_two_tone_split_matches_the_amplitudes",
            "test_two_tone_split_can_fail",
            "test_flat_spectrum_fills_bands_in_proportion_to_width",
            "test_percentages_sum_to_one_hundred",
            "test_summing_to_one_hundred_proves_nothing",
            "test_the_spectrum_integrates_to_the_time_domain_energy",
            "test_parseval_check_can_fail",
            "test_band_power_weights_partial_bins",
            "test_partial_bin_weighting_can_fail",
            "test_parseval_holds_with_direct_current_and_nyquist_content",
            "test_doubling_direct_current_and_nyquist_can_fail",
            "test_each_band_energy_survives_the_round_trip",
            "test_the_round_trip_check_can_fail",
            "test_percentages_do_not_move_under_a_gain_change",
            "test_percentages_move_when_the_balance_moves",
            "test_sample_rate_does_not_change_the_percentages",
            "test_sample_rate_invariance_can_fail",
            "test_content_below_20_hz_stays_out_of_the_bands",
            "test_content_below_20_hz_staying_out_can_fail",
            "test_the_transform_keeps_every_frame",
            "test_zero_padding_does_not_move_the_answer",
            "test_a_file_shorter_than_the_minimum_has_no_spectral_measurement",
            "test_an_independent_filterbank_agrees_on_a_controlled_signal",
            "test_the_filterbank_check_can_fail",
        ),
    ),
    Method(
        id="levels/gated-crest-dc-clipping",
        measures="crest factor, direct current offset, clipped runs, samples over full scale",
        computed_from="sample peak from the decoded samples, root mean square over exactly the "
        "blocks the loudness gate kept, direct current as a per channel mean and as the largest "
        "400 ms block mean, full scale runs counted against the largest magnitude the source bit "
        "depth can represent.",
        failure_modes=(
            "A crest taken against an ungated root mean square rewards silence. Appending 30 s of "
            "silence to a 20 s tone moves the ungated figure by 3.98 dB. The gated figure moves "
            "0.033 dB, which is the blocks straddling the transition and is bounded by "
            "10 log10((N+4)/N), 0.087 dB for that material. It is not zero and cannot be.",
            "The gate is the loudness gate rather than a second one invented here, so crest is "
            "reported for the programme as the loudness figure defines programme. It also means a "
            "fault in that gate moves both numbers, which is why the gate carries its own "
            "controls.",
            "Full scale is not symmetric in integer PCM and a threshold set anywhere above the "
            "largest positive code is wrong in one direction only. At 16 bit the positive extreme "
            "is 32767/32768 and the negative extreme is exactly -1.0, so a threshold of 1.0, or "
            "of one minus half a quantisation step, never fires on a positive peak and always "
            "fires on a negative one. On a symmetrically clipped master that reports half the "
            "truth, and half is a plausible number that nobody questions. The threshold is the "
            "largest magnitude the source bit depth can represent, and 1.0 only when the depth is "
            "unknown.",
            "Counting individual samples at full scale flags every peak normalised master as "
            "damaged. Runs of three or more, and a peak normalised file reads zero.",
            "Lossy decoding goes past full scale. The reference mp3 here decodes to +1.0 dBFS. "
            "Those samples are counted separately rather than folded into the clipping figure, "
            "because they describe the codec and not the master.",
            "Direct current over a whole file with a fade is the mean of a signal that is not "
            "stationary. A file stepping from +0.1 to -0.1 has a mean of zero and a largest block "
            "mean of 0.1. Both are reported.",
        ),
        cross_check="No second instrument. Direct current and the run counter are exact counts "
        "over the decoded samples, with nothing to compare them against but signals built with a "
        "known offset and a known number of runs. Crest has one analytic answer: a sine is "
        "exactly 3.0103 dB, and a square is 0.",
        controls=(
            "test_crest_of_a_sine_is_three_decibels",
            "test_crest_of_a_square_can_fail",
            "test_crest_does_not_move_when_silence_is_appended",
            "test_the_silence_invariance_can_fail",
            "test_dc_offset_reads_the_offset",
            "test_dc_offset_can_fail",
            "test_dc_offset_block_max_sees_a_step_the_mean_hides",
            "test_clipped_runs_counts_runs_not_samples",
            "test_clipped_runs_can_fail",
            "test_clip_threshold_follows_bit_depth",
            "test_over_full_scale_samples_are_counted",
            "test_silence_has_no_crest",
        ),
    ),
    Method(
        id="stereo/energy-weighted-correlation",
        measures="left to right correlation, and side to mid energy ratio",
        computed_from="sums over the whole file of the mean removed channels. Correlation is "
        "sum(LR) over the root of sum(L squared) times sum(R squared). Width is ten log of side "
        "energy over mid energy, with mid the half sum and side the half difference.",
        failure_modes=(
            "The predicted trap was correlation on near silent frames reading noise over noise. "
            "It is not gated away here, it is removed: one energy weighted figure over the whole "
            "file cannot be dominated by quiet passages, because they carry almost no energy. "
            "Averaging per frame correlations is what creates that problem, and nothing here "
            "averages per frame.",
            "Direct current correlates two channels that are otherwise independent. The channels "
            "are mean removed first, so 0.2 of offset moves the figure by under 1e-4 where the "
            "raw version moves it far enough to read as a different record.",
            "Identical channels have no side energy and channels that cancel have no mid energy. "
            "Neither ratio exists in decibels, so the field is absent rather than infinite.",
            "A mono file has no left and right. There is no stereo block at all, rather than a "
            "correlation of 1.0, which is a value a real stereo master can legitimately have.",
            "Side over mid is a definition, not a standard. No two tools agree on what a width "
            "figure means, so this one says what it computes and can only be compared with "
            "itself.",
        ),
        cross_check="An analytic mix. Two channels built from a shared source and independent "
        "noise have correlation a squared over a squared plus b squared, and side over mid of b "
        "squared over two, over a squared plus b squared over two. Both are known before the file "
        "exists and neither involves the code.",
        controls=(
            "test_correlation_of_identical_channels_is_one",
            "test_correlation_of_inverted_channels_is_minus_one",
            "test_correlation_matches_the_mix_ratio",
            "test_correlation_can_fail",
            "test_correlation_does_not_move_under_direct_current",
            "test_the_direct_current_invariance_can_fail",
            "test_width_matches_the_mix_ratio",
            "test_width_can_fail",
            "test_identical_channels_have_no_width",
            "test_a_mono_file_has_no_stereo_measurement",
        ),
    ),
    Method(
        id="tempo/flux-envelope-phase-track",
        measures="tempo in beats per minute, the octave and ternary alternatives, grid fit in "
        "milliseconds, how many onsets were fitted, and whether the tempo moves across the track",
        computed_from="A spectral flux envelope at 100 Hz. Each of eight log spaced bands is "
        "divided by its own mean before summing, so a static gain in any band cannot move the "
        "result. The rate is the peak of a transform of that envelope, scored on the beat rate "
        "and its second and fourth harmonics. Onsets are local maxima of the envelope. Drift is "
        "a cubic fit of beat index against time, so the derivative is the tempo at each "
        "moment and the reported range is the smallest and largest that derivative reaches "
        "anywhere across the file. The curve itself comes from short window estimates across "
        "the file. The onsets choose the stretch it is read over and give the fit its "
        "uncertainty, but they do not shape it: reading the windowed curve instead of the "
        "onset fitted one moves the span by at most 0.036 BPM on the known answer set and "
        "0.013 on real material, against a floor of 0.4.",
        failure_modes=(
            "The 55 to 200 BPM search range is a prior on where the beat is, not a bound on "
            "where to look. It selects an octave before any of the reasoning below runs. On one "
            "reference the strongest rate over 40 to 400 BPM is 244.00 and the range reports "
            "122.00, which is the better answer arrived at by clipping. A peak that lands on "
            "either end of the grid is a truncation rather than a maximum, so the rate falls "
            "back to the best interior turning point and the file carries a caveat saying so.",
            "The octave is a musical judgement, not a property of the signal. A kick every beat "
            "at 72 with a hat every half beat gives a grid at 144 that is a perfect fit: every "
            "tick has an onset and every onset is on a tick. On 35 controls with known answers "
            "this rule returns the double 8 times, every one of them between 72 and 88 BPM on "
            "subdivided material. The alternatives are reported with their occupancy and "
            "coverage so the choice is visible rather than hidden. The margin between the "
            "top two candidates does not say which is right: across the same 35 controls "
            "the correct answer has been reached on a 0.6 percent margin and the wrong one "
            "on 29.0 percent, so no threshold on it is shipped.",
            "A grid fit is measured only over onsets within 30 ms of a tick, so it is the median "
            "of a truncated distribution and cannot exceed about 15 ms however loose the timing "
            "is. Measured on a click track it reads 4.07, 9.09, 11.18 and 15.52 ms for scatter "
            "of 0, 10, 20 and 40 ms. Coverage over the same four is 1.000, 0.992, 0.852 and "
            "0.570. Below about 10 ms read the grid fit, above it read the coverage.",
            "Onset times carry a fixed offset of about 8 ms early, because a transient raises a "
            "frame as soon as it enters the window rather than when it reaches the centre. It "
            "cancels in tempo, which is a period, and in grid fit, which is measured against a "
            "fitted phase. It would not cancel in an absolute onset time, which is why none is "
            "reported.",
            "Drift is a cubic in beat index, so tempo is a parabola in time. Checked against "
            "tempo maps written into a MIDI file and read back out of it, a steady track, two "
            "straight ramps and an arch that rises 6 BPM and returns are all held to within "
            "0.25 BPM or 10 percent. Shapes that are not a parabola are not held: an "
            "exponential slowdown of 18.99 BPM reads 13.52, and a step of 4.00 BPM reads 7.20. "
            "A sudden tempo change reads as a larger gradual one.",
            "The range is the smallest and largest the fitted tempo reaches anywhere across "
            "the file, not the difference between its two ends. Taken at the ends, any shape "
            "that returns to where it started is exactly zero however well the curve fits, so "
            "a track moving 6 BPM reported as steady.",
            "The 0.4 BPM drift floor is measured, not derived. Across 56 steady controls the "
            "largest span was 0.350. Every one above 0.15 was 90 seconds long and none of the "
            "150 second ones came near, so the floor is conservative for a full length track. "
            "The uncertainty the fit reports for itself is about 0.02 BPM and understates, "
            "because the residuals carry systematic structure the fit absorbs. Correcting it "
            "for residual autocorrelation, measured at 0.17, inflates it by only 1.19 and does "
            "not close the gap. It is reported for information and is not the gate.",
            "Dividing each band by its own mean is what makes the reading immune to a shelf, "
            "but not at the size a gentle control shows. Flux is a difference of log "
            "magnitudes, so a static gain adds a constant that largely cancels on its own, and "
            "at 2 dB the raw sum is invariant too. The two part company at 6 dB and above: "
            "over 60 shelved renders up to 12 dB the normalised envelope moved 0.000 BPM and "
            "the raw sum moved up to 0.120. The control shelves at 12 dB for that reason, "
            "because at 2 dB it cannot tell the two apart. The normalisation also gives every "
            "band the same weight whatever it contains, so a band with almost no content "
            "counts as much as the one carrying the kick.",
            "Onset detection needs a threshold that cannot collapse. A median absolute deviation "
            "is exactly zero on a sparse envelope, where most samples sit at the same floor, so "
            "it is not used. The threshold is the median plus a multiple of the mean positive "
            "excursion, which is nonzero for any signal with an onset in it.",
        ),
        cross_check="None at runtime, and the gap is deliberate. A second stage was built to "
        "resolve the octave from onset occupancy and coverage. Measured against 35 known "
        "answers it resolved the octave worse than not having it, 25 right against 27, so it "
        "reports fit quality only and does not choose. A number that looks checked and is not "
        "would be worse than the gap.",
        controls=(
            "test_a_click_track_reads_its_own_tempo",
            "test_a_rate_at_the_search_boundary_is_declared",
            "test_a_rate_inside_the_range_carries_no_caveat",
            "test_the_tempo_control_can_fail",
            "test_onset_spacing_matches_the_beat_period",
            "test_onset_count_matches_the_click_count",
            "test_the_onset_threshold_survives_a_sparse_envelope",
            "test_tempo_does_not_move_under_a_shelf",
            "test_the_shelf_invariance_can_fail",
            "test_grid_fit_widens_with_jitter",
            "test_the_grid_fit_comparison_can_fail",
            "test_grid_fit_saturates_and_coverage_does_not",
            "test_the_double_leaves_half_its_ticks_empty",
            "test_the_alternatives_carry_the_octave_relations",
            "test_drift_reads_a_known_ramp",
            "test_the_drift_control_can_fail",
            "test_drift_sees_a_tempo_that_comes_back",
            "test_the_returning_tempo_is_not_read_as_steady",
            "test_a_steady_track_reports_no_drift",
            "test_a_steady_track_stays_under_the_declared_horizon",
            "test_tempo_does_not_depend_on_the_sample_rate",
            "test_a_short_file_has_no_tempo",
            "test_silence_has_no_tempo",
        ),
    ),
    Method(
        id="master/gain-cut-and-searched-limiter",
        measures="nothing. It is the one method here that changes a signal rather than "
        "reading one, and it is listed so that what it changes has the same registry entry "
        "every measurement has.",
        computed_from="the same Measurement and Target the rest of the bench produces. A low "
        "cut at 20 Hz when the file reports more energy below it than a percentage is "
        "reported to. A gain from the distance between the measured loudness and the near "
        "edge of the target range. A ceiling from the target's own true peak limit. Attack "
        "and release from a search over four attacks and three releases, keeping the "
        "settings whose output leaves every band's verdict against the target where it was "
        "and choosing the one that moved the balance least.",
        failure_modes=(
            "A correction aimed exactly at a boundary is not inside it. Every aim clears its "
            "boundary by two of the measurement's uncertainties plus the crosscheck tolerance "
            "the bench declares for that field, because the plan is built by the second "
            "instrument in memory and the verdict is taken from the primary instrument "
            "reading the written file. Entries 26 and 28.",
            "Limiting removes loudness, and how much depends on the material inside the "
            "attack window rather than on anything the gain arithmetic can see. The gain is "
            "corrected across measured passes and stops when the measurement clears the "
            "floor, not when a formula says it should have.",
            "The search criterion is verdicts against the target. A target that bounds no "
            "band or rollup gives a criterion no setting can fail, which would accept "
            "everything and report a count that reads like evidence. It refuses to choose "
            "instead, and says so. Entry 27.",
            "Loudness that the limiter cannot reach without changing a verdict is not "
            "reached. The plan says how much is missing rather than reporting the run as "
            "done because it ran.",
            "A gain derived only from a floor would move a file that is already inside its "
            "target down to the edge of it. A file inside its target is left alone. Entry 30.",
            "The low cut moves the bands above it by an amount that depends on how much is "
            "below 20 Hz, so the plan measures what it moved on the file in hand rather than "
            "carrying a residual over from other tracks. Entry 32.",
            "It can write a file that is worse. Nothing here judges the result by ear, and "
            "the verdicts it reports are against a target seeded from three lossy references.",
        ),
        cross_check="It measures what it wrote, from the file on disk and with both "
        "instruments, and checks the output against what the plan predicted using the "
        "instrument that made the prediction. The before and after comparisons are the same "
        "comparison the folder table uses.",
        controls=(
            "test_it_refuses_to_write_into_the_folder_the_source_is_in",
            "test_it_refuses_the_folder_however_the_path_is_spelled",
            "test_it_refuses_to_replace_a_master_it_made_before",
            "test_the_refusal_is_not_blanket",
            "test_the_input_is_the_same_file_afterwards",
            "test_that_byte_check_can_fail",
            "test_the_aim_leaves_a_whole_step_of_daylight",
            "test_aiming_by_one_uncertainty_leaves_none",
            "test_the_clearance_covers_the_gap_between_the_two_instruments",
            "test_a_low_cut_is_applied_when_there_is_something_under_20_hz",
            "test_a_low_cut_is_refused_when_there_is_not",
            "test_the_plan_reports_what_the_cut_actually_moved",
            "test_that_reported_movement_is_not_the_same_for_any_filter",
            "test_the_gain_is_derived_from_the_signal_the_cut_left",
            "test_that_check_can_tell_the_two_signals_apart",
            "test_no_gain_when_the_target_says_nothing_about_loudness",
            "test_no_gain_when_the_file_is_already_inside_the_range",
            "test_a_file_above_its_range_is_brought_to_the_top_and_not_the_bottom",
            "test_a_file_below_its_range_is_raised",
            "test_render_does_only_what_the_plan_says",
            "test_a_target_that_bounds_no_band_refuses_to_limit",
            "test_a_target_that_bounds_bands_does_search",
            "test_a_prediction_is_checked_against_the_instrument_that_made_it",
            "test_checking_it_against_the_other_one_would_not_hold",
            "test_the_file_started_outside_the_target",
            "test_the_output_is_measured_and_the_prediction_holds",
            "test_the_peak_lands_inside_the_ceiling_not_on_it",
            "test_the_loudness_lands_inside_the_target",
            "test_that_file_really_needs_the_correction",
            "test_that_file_really_cannot_converge",
            "test_a_correction_that_cannot_converge_is_bounded",
            "test_the_correction_reaches_the_target_it_aims_at",
            "test_the_correction_stops_with_room_and_not_on_the_condition",
            "test_it_says_where_it_landed",
            "test_a_target_it_cannot_reach_is_reported_as_not_reached",
            "test_it_says_what_the_limiter_took",
            "test_the_peak_it_limits_is_the_one_between_samples",
            "test_reading_samples_instead_would_fail_this",
            "test_a_signal_under_the_ceiling_is_returned_untouched",
            "test_that_untouched_check_can_fail",
            "test_the_lookahead_is_wider_than_the_smoothing",
            "test_that_property_is_the_lookahead_and_not_luck",
            "test_the_release_takes_the_time_it_says",
            "test_the_release_check_can_fail",
            "test_the_reduction_lands_on_the_peak_not_after_it",
            "test_that_alignment_check_can_fail",
            "test_what_it_reports_about_its_own_work",
            "test_the_envelope_meets_the_ceiling_without_the_trim",
            "test_the_ceiling_check_can_fail",
        ),
    ),
)

METHODS = {m.id: m for m in _METHODS}


def get(method_id: str) -> Method:
    try:
        return METHODS[method_id]
    except KeyError:
        raise KeyError(f"no method registered as {method_id!r}") from None


def render_markdown() -> str:
    out = []
    for m in _METHODS:
        out.append(f"### `{m.id}`\n")
        out.append(f"**Measures** {m.measures}\n")
        out.append(f"**From** {m.computed_from}\n")
        out.append("**How it would lie**\n")
        out.extend(f"- {f}" for f in m.failure_modes)
        out.append("")
        out.append(f"**Cross check** {m.cross_check}\n")
        out.append("**Controls** " + ", ".join(f"`{c}`" for c in m.controls) + "\n")
    return "\n".join(out)


if __name__ == "__main__":
    print(render_markdown())
