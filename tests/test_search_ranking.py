import unittest

from search_ranking import calculate_search_relevance, select_best_search_match


class SearchRankingTests(unittest.TestCase):
    def test_title_and_artist_query_beats_first_deezer_result(self):
        candidates = [
            {
                'id': 1,
                'title': 'MEGAVERSE',
                'artist': {'name': 'Stray Kids'},
            },
            {
                'id': 2,
                'title': 'Hooligan',
                'artist': {'name': 'Big Baby Tape'},
            },
        ]

        result = select_best_search_match(
            'Hooligan big baby tape',
            candidates,
            title_field='title',
            artist_field='artist',
        )

        self.assertEqual(result['id'], 2)

    def test_irrelevant_result_is_rejected(self):
        candidates = [
            {
                'id': 1,
                'title': 'MEGAVERSE',
                'artist': {'name': 'Stray Kids'},
            },
        ]

        result = select_best_search_match(
            'Hooligan big baby tape',
            candidates,
            title_field='title',
            artist_field='artist',
        )

        self.assertIsNone(result)

    def test_matching_title_with_wrong_artist_is_rejected(self):
        candidates = [
            {
                'id': 1,
                'title': 'Hooligan',
                'artist': {'name': 'Big Baby Tape'},
            },
        ]

        result = select_best_search_match(
            'Hooligan Drake',
            candidates,
            title_field='title',
            artist_field='artist',
        )

        self.assertIsNone(result)

    def test_album_name_is_selected_instead_of_first_result(self):
        candidates = [
            {
                'id': 1,
                'title': 'ROCK-STAR',
                'artist': {'name': 'Stray Kids'},
            },
            {
                'id': 2,
                'title': 'ILOVEBENZO',
                'artist': {'name': 'Big Baby Tape'},
            },
        ]

        result = select_best_search_match(
            'ILOVEBENZO',
            candidates,
            title_field='title',
            artist_field='artist',
        )

        self.assertEqual(result['id'], 2)

    def test_typo_in_long_word_is_tolerated(self):
        score = calculate_search_relevance(
            'Holigan Big Baby Tape',
            'Hooligan',
            'Big Baby Tape',
        )

        self.assertGreaterEqual(score, 80)

if __name__ == '__main__':
    unittest.main()
