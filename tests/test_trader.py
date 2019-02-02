import unittest



class TestTrader(unittest.TestCase):
    def setUp(self):
        self.basic_book = {
            "bids":{
                1: (10, 100),
                2: (11, 100)
            },
            "asks": {
                3: (12, 100),
                4: (13, 100)
            }
        }

        self.cancellable_book = {
            "bids": {
                0: (9, 100),
                1: (10, 100),
                2: (10, 50),
                3: (11, 100)
            },
            "asks": {
                4: (12, 100),
                5: (13, 100),
                6: (13, 50),
                7: (14, 100)
            }
        }
    

    def test_get_trades_for_ideal_book_simple_add(self):
        from trader import get_trades_for_ideal_book as gt

        # Basic add bid and ask
        basic_ideal = {
            "bids": [(10, 100), (11, 100), (9, 100)],
            "asks": [(12, 100), (13, 100), (14, 100)]
        }

        trades = gt(self.basic_book, basic_ideal)

        self.assertEqual(trades, {
            "bids": [(9, 100)],
            "asks": [(14, 100)],
            "cancels": []
        })
    
    def test_get_trades_for_ideal_book_increase_at_price(self):
        from trader import get_trades_for_ideal_book as gt

        increase_ideal = {
            "bids": [(10, 110), (11, 100)],
            "asks": [(12, 110), (13, 100)]
        }

        trades = gt(self.basic_book, increase_ideal)

        self.assertEqual(trades, {
            "bids": [(10, 10)],
            "asks": [(12, 10)],
            "cancels": []
        })
    
    def test_get_trades_for_ideal_book_simple_cancel(self):
        from trader import get_trades_for_ideal_book as gt

        cancel_ideal = {
            "bids": [(10, 75), (11, 50)],
            "asks": [(13, 75), (14, 50)]
        }

        trades = gt(self.cancellable_book, cancel_ideal)

        self.assertEqual(trades, {
            "bids": [(10, 25), (11, 50)],
            "asks": [(13, 25), (14, 50)],
            "cancels": [0, 1, 3, 4, 5, 7]
        })
    
    def test_get_trades_for_idea_book_max_trade(self):
        from trader import get_trades_for_ideal_book as gt

        max_ideal = {
            "bids": [(10, 149), (11, 7)],
            "asks": [(12, 149), (13, 7)]
        }

        trades = gt(self.basic_book, max_ideal, max_trade=25)

        self.assertEqual(trades, {
            "bids": [(10, 25), (10, 24), (11, 7)],
            "asks": [(12, 25), (12, 24), (13, 7)],
            "cancels": [2, 4]
        })