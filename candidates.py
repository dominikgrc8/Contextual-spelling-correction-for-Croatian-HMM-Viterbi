"""Generation of correction candidates for suspicious words."""
import itertools
import string
import time

from api import fetch_ngram_data


def generate_edit_distance_1(word):
    letters = string.ascii_lowercase + "čćžšđ"
    edits = set()

    splits = []
    for i in range(len(word) + 1):
        left = word[:i]
        right = word[i:]
        splits.append((left, right))

    for left, right in splits:
        if right:
            edits.add(left + right[1:])

    for left, right in splits:
        if len(right) > 1:
            swapped = right[1] + right[0] + right[2:]
            edits.add(left + swapped)

    for left, right in splits:
        if right:
            for c in letters:
                edits.add(left + c + right[1:])

    for left, right in splits:
        for c in letters:
            edits.add(left + c + right)

    return edits


def generate_letter_alternatives(letters, word):
    group = set(letters)
    options = []

    for char in word:
        if char in group:
            options.append(list(group))
        else:
            options.append([char])
    combinations = itertools.product(*options)
    final = []
    for combo in combinations:
        new_word = ''.join(combo)

        data = fetch_ngram_data(new_word)
        count = data.get("count")
        if count is not None and int(count) > 50:
            final.append(new_word)

    return final


def context_count(words, i, w, sus_positions):
    # Count of candidate w together with a neighbour: the left one if it is trusted,
    # otherwise the right one, falling back to the left one when w is the last word.
    if i != 0 and (i - 1 not in sus_positions or i + 1 >= len(words)):
        data = fetch_ngram_data(f'{words[i-1]} {w}')
    else:
        data = fetch_ngram_data(f'{w} {words[i+1]}')
    return 0 if data.get("count", 0) is None else int(data.get("count", 0))


def generate_corrections_with_korpus_only_sus(segments, sus_by_segments, word_map, korpus):
    # corrections[s][i] is the list of candidates for word i of segment s; the original word is always first.
    corrections = []
    problematic = "ćčc"
    problematic_capital = "ĆČC"
    best = 0
    for index, segment in enumerate(segments):
        words = segment.split()
        segment_corrections = [[word] for word in words]
        corrections.append(segment_corrections)
        if len(words) > 1:
            for i, word in enumerate(words):
                start = time.perf_counter()
                recommendations = []
                if i in sus_by_segments[index]:
                    sus = word

                    if sus in word_map:
                        recommendations = [w for w in word_map[sus] if w != sus]

                    else:
                        if any(char in sus for char in problematic):
                            recommendations.extend(generate_letter_alternatives(problematic, sus))
                        if any(char in sus for char in problematic_capital):
                            recommendations.extend(generate_letter_alternatives(problematic_capital, sus))
                        distance1 = generate_edit_distance_1(sus)
                        for w in distance1:
                            if w.upper() in korpus:
                                if context_count(words, i, w, sus_by_segments[index]):
                                    recommendations.append(w)
                        if len(recommendations) < 2:
                            distance2 = []
                            for e1 in distance1:
                                distance2.extend(generate_edit_distance_1(e1))
                            for w in distance2:
                                if w.upper() in korpus:
                                    if i != 0:
                                        data = fetch_ngram_data(f'{words[i-1]} {w}')
                                        count = 0 if data.get("count", 0) is None else int(data.get("count", 0))
                                    else:
                                        data = fetch_ngram_data(f'{w} {words[i+1]}')
                                        count = 0 if data.get("count", 0) is None else int(data.get("count", 0))

                                    if count:
                                        recommendations.append(w)

                for item in recommendations:
                    if item not in segment_corrections[i]:
                        segment_corrections[i].append(item)
                end = time.perf_counter()
                timing = end-start
                if timing >= best:
                    best = timing
    return corrections, best
