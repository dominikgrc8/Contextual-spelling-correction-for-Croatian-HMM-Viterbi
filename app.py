import itertools
import math
import string
from functools import lru_cache
from flask import Flask, render_template, request
from markupsafe import Markup, escape
import re
import requests
import time
import json

app = Flask(__name__)

API_TIMEOUT = 5  # seconds

@app.route("/", methods=['GET', 'POST'])
def index():
    message = None
    user_input = None
    output = None
    timing = f''
    with open("static/word_map.json", "r", encoding="utf-8") as f:
        word_map = json.load(f)

    try:
        with open("static/types.lang.utf8", "r", encoding="utf-8") as f:
            korpus = set(word.strip() for word in f if word.strip())
    except FileNotFoundError:
        file_content = ""
        message = "Greška: Datoteka nije pronađena."


    if request.method == 'POST':
        user_input = request.form['user_input']
        mode_on = 'mode_switch' in request.form

        start1 = time.perf_counter()
        ngrams, segments = tokenize(user_input)
        end1 = time.perf_counter()
        sus_by_segments, fetch_time = find_sus_by_segments(segments, word_map)
        start2 = time.perf_counter()
        corr_dict2, generating_time = generate_corrections_with_korpus_only_sus(segments, sus_by_segments, word_map, korpus)
        end2 = time.perf_counter()
        start3 = time.perf_counter()
        transitions, transitions_time = transition_matrix2(segments, corr_dict2)
        end3 = time.perf_counter()
        start4 = time.perf_counter()
        corrected_list = viterbi2(segments, corr_dict2, transitions)
        end4 = time.perf_counter()


        if mode_on:
            message = f"{print_dict_list(corr_dict2)}\n\n\n{print_nested_dict(transitions)}"
            timing += f'Time\n'
            timing += f'Tokenizacija: {end1-start1}\n'
            timing += f'API dohvat frekvencija: {fetch_time}\n'
            timing += f'Najdulje vrijeme generiranja za jednu riječ: {generating_time}\n'
            timing += f'Ukupno vrijeme generiranja: {end2-start2}\n'
            timing += f'Najdulje računanje tranzicija za jedan segment: {transitions_time}\n'
            timing += f'Ukupno računanje tranzicijskih vjerojatnosti: {end3-start3}\n'
            timing += f'Viterbi algoritam: {end4-start4}\n'
        output = pair_lists_to_highlighted_html(segments, corrected_list, corr_dict2)


    return render_template('index.html', message=message, user_input=user_input, output=output, timing=timing)


def tokenize(text):

    segments = re.split(r'[.,:;!?()"\n]+', text)
    cleaned = []
    for segment in segments:
        if segment:
            cleaned.append(segment.strip())

    for i in range(len(cleaned)):
        words = cleaned[i].split()
        if words:
            words[0] = words[0].lower()
            cleaned[i] = ' '.join(words)

    ngrams = {"unigrams" : [],
              "bigrams": []}
    for segment in cleaned:
        words = segment.split()

        for word in words:
            ngrams["unigrams"].append(word)

        if len(words) >= 2:
            for i in range(len(words) - 1):
                bigram = words[i] + ' ' + words[i + 1]
                ngrams["bigrams"].append(bigram)


    return ngrams, cleaned


@lru_cache(maxsize=100_000)
def _fetch_ngram_data_cached(ngram):
    # Raises on any failure; lru_cache does not store exceptions, so only successful responses are cached.
    url = "https://ispravi.me/api/ngram"
    response = requests.post(url, data={"ngram": ngram}, timeout=API_TIMEOUT)
    response.raise_for_status()
    return response.json()


def fetch_ngram_data(ngram):
    try:
        return _fetch_ngram_data_cached(ngram)
    except requests.exceptions.HTTPError as e:
        return {"error": f"Server vratio status {e.response.status_code}", "details": e.response.text}
    except ValueError:
        return {"error": "Odgovor nije validan JSON"}
    except requests.exceptions.RequestException as e:
        return {"error": "Greška u zahtevu", "details": str(e)} #timeout, connection error...

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

def find_sus_by_segments(segments, word_map):
    sus_by_segments = []
    for segment in segments:
        element = []
        i = segments.index(segment)
        for word in segment.split():
            start = time.perf_counter()
            data = fetch_ngram_data(word)
            end = time.perf_counter()
            if data and (data.get("count", 0) == None or int(data.get("count", 0)) < 100):
                element.append(word)
            else:
                if word in word_map:
                    element.append(word)
        words = segment.split()
        if len(words) >= 2:
            for i in range(len(words) - 1):
                bigram = words[i] + ' ' + words[i + 1]
                if bigram.split()[1] not in element and bigram.split()[0] not in element:
                    data = fetch_ngram_data(bigram)
                    if data and (data.get("count", 0) == None or int(data.get("count", 0)) < 50):
                        element.append(bigram.split()[1])

        sus_by_segments.append(element)
    return(sus_by_segments, end-start)


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
        if data and (data.get("count", 0) != None or (0 if data.get("count", 0) is None else int(data.get("count", 0))) > 50):
            final.append(new_word)

    return final



def generate_corrections_with_korpus_only_sus(segments, sus_by_segments, word_map, korpus):
    corrections_dict = {}
    problematic = "ćčc"
    problemati_capital = "ČĆC"
    for segment in segments:
        index = segments.index(segment)
        words = segment.split()
        if len(words) > 1:
            best = 0
            for word in words:
                start = time.perf_counter()
                recommendations = []
                corrections_dict[word] = [word]
                sus = None
                if word in sus_by_segments[index]:
                    sus = word

                    letter_corrections = None
                    if sus in word_map:
                        if sus in word_map[sus]:
                            recommendations = word_map[sus]
                            recommendations.remove(sus)
                        else:
                            recommendations = word_map[sus]

                    else:
                        if any(char in sus for char in problematic):
                            letter_corrections = generate_letter_alternatives(problematic, sus)
                            corrections_dict[sus].extend(letter_corrections)
                        if any(char in sus for char in problemati_capital):
                            letter_corrections = generate_letter_alternatives(problematic, sus)
                            corrections_dict[sus].extend(letter_corrections)
                        distance1 = generate_edit_distance_1(sus)
                        for w in distance1:
                            if w.upper() in korpus:
                                i = words.index(word)
                                if i != 0 and words[i-1] not in sus_by_segments[index]:
                                    data = fetch_ngram_data(f'{words[i-1]} {w}')
                                    count = 0 if data.get("count", 0) is None else int(data.get("count", 0))
                                else:
                                    data = fetch_ngram_data(f'{w} {words[i+1]}')
                                    count = 0 if data.get("count", 0) is None else int(data.get("count", 0))

                                if count:
                                    recommendations.append(w)
                        if len(recommendations) < 2:
                            distance2 = []
                            for e1 in distance1:
                                distance2.extend(generate_edit_distance_1(e1))
                            for w in distance2:
                                if w.upper() in korpus:
                                    i = words.index(word)
                                    if i != 0:
                                        data = fetch_ngram_data(f'{words[i-1]} {w}')
                                        count = 0 if data.get("count", 0) is None else int(data.get("count", 0))
                                    else:
                                        data = fetch_ngram_data(f'{w} {words[i+1]}')
                                        count = 0 if data.get("count", 0) is None else int(data.get("count", 0))

                                    if count:
                                        recommendations.append(w)



                else:
                    if sus in word_map:
                        recommendations = word_map[sus]

                for item in recommendations:
                    if item not in corrections_dict[word]:
                        corrections_dict[word].append(item)
                end = time.perf_counter()
                timing = end-start
                if timing >= best:
                    best = timing
    return corrections_dict, best


def transition_matrix2(segments, correction_dict):
    transitions = {}
    best = 0
    for segment in segments:
        start = time.perf_counter()
        words = segment.split()
        n = len(words)

        for i in range(1, n):
            prev_word_candidates = correction_dict.get(words[i-1], [words[i-1]])
            curr_word_candidates = correction_dict.get(words[i], [words[i]])

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

    return transitions, timing


def viterbi2(segments, correction_dict, transitions):
    result_list = []

    for segment in segments:
        words = segment.split()
        n = len(words)

        V = []  # Viterbi table
        backpointer = []
        for i in range(n):
            V.append({})
            backpointer.append({})

        first_candidates = correction_dict.get(words[0], [words[0]])
        for w in first_candidates:
            V[0][w] = 1e-12
            backpointer[0][w] = None

        # Recursion
        for t in range(1, n):
            curr_candidates = correction_dict.get(words[t], [words[t]])
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

def print_dict_list(data):
    output = ""
    for key, values in data.items():
        output += f"{key}:\n"
        if isinstance(values, (list, set, tuple)):
            for value in values:
                output += f"{value}\n"
        else:
            output += f"{values}\n"
        output += "\n\n"
    return output

def print_nested_dict(nested_dict):
    output = ""
    for outer_key, inner_dict in nested_dict.items():
        output += f"{outer_key}:\n"
        if isinstance(inner_dict, dict):
            for inner_key, value in inner_dict.items():
                output += f"  {inner_key}: {value}\n"
        else:
            output += f"  {inner_dict}\n"
        output += "\n"
    return output


def pair_lists_to_highlighted_html(original_list, corrected_list, corrections_dict):
    html_output = ""

    for segment, corrected_words in zip(original_list, corrected_list):
        original_words = segment.split()
        original_line = ""
        corrected_line = ""

        for orig_word, corr_word in zip(original_words, corrected_words):
            if orig_word in corrections_dict and len(corrections_dict[orig_word]) > 1:
                original_line += f'<span class="incorrect">{escape(orig_word)}</span> '
                corrected_line += f'<span class="corrected">{escape(corr_word)}</span> '
            else:
                original_line += f'{escape(orig_word)} '
                corrected_line += f'{escape(corr_word)} '

        html_output += f"<div class='segment-block'>"
        html_output += f"<div><strong>Originalno:</strong> {original_line.strip()}</div>"
        html_output += f"<div><strong>Ispravljeno:</strong> {corrected_line.strip()}</div>"
        html_output += f"</div><br>"

    # Every user-supplied word above went through escape(), so the result is safe to render as HTML.
    return Markup(html_output.strip())


if __name__ == "__main__":
    app.run()
