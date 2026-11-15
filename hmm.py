"""Transition probabilities and Viterbi decoding over correction candidates."""
import math
import time

from api import fetch_ngram_data


def transition_matrix2(segments, corrections):
    transitions = {}
    best = 0
    for index, segment in enumerate(segments):
        start = time.perf_counter()
        words = segment.split()
        n = len(words)

        for i in range(1, n):
            prev_word_candidates = corrections[index][i-1]
            curr_word_candidates = corrections[index][i]

            for prev_word in prev_word_candidates:
                for curr_word in curr_word_candidates:
                    key = (prev_word, curr_word)
                    ngram = f"{prev_word} {curr_word}"
                    data = fetch_ngram_data(prev_word)
                    count_prev = 999999 if data.get("count", 999999) is None else int(data.get("count", 999999))

                    data = fetch_ngram_data(ngram)
                    count_ngram = 0 if data.get("count", 0) is None else int(data.get("count", 0))

                    prob = count_ngram / count_prev if count_prev > 0 else 1e-6

                    transitions[key] = prob
        end = time.perf_counter()
        timing = end-start
        if timing >= best:
            best = timing

    return transitions, best


def viterbi2(segments, corrections, transitions):
    result_list = []

    for index, segment in enumerate(segments):
        words = segment.split()
        n = len(words)

        V = []  # Viterbi table
        backpointer = []
        for i in range(n):
            V.append({})
            backpointer.append({})

        first_candidates = corrections[index][0]
        for w in first_candidates:
            V[0][w] = 1e-12
            backpointer[0][w] = None

        # Recursion
        for t in range(1, n):
            curr_candidates = corrections[index][t]
            prev_candidates = V[t-1].keys()

            for curr_word in curr_candidates:
                max_prob = float('-inf')
                best_prev = None

                for prev_word in prev_candidates:
                    trans_prob = transitions.get((prev_word, curr_word), 1e-6)
                    prob = V[t-1][prev_word] + math.log(trans_prob + 1e-12)

                    if prob > max_prob:
                        max_prob = prob
                        best_prev = prev_word

                V[t][curr_word] = max_prob
                backpointer[t][curr_word] = best_prev

        # Backtrace
        last_t = n - 1
        if not V[last_t]:
            result_list.append(words)
            continue

        best_final_word = max(V[last_t], key=V[last_t].get)
        path = [best_final_word]

        for t in range(last_t, 0, -1):
            best_final_word = backpointer[t][best_final_word]
            path.insert(0, best_final_word if best_final_word is not None else words[t-1])

        result_list.append(path)

    return result_list
