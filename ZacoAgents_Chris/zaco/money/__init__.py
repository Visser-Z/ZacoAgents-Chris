"""Exact money: splitting an amount so the pieces add back up to it.

Section 8 is unusually specific about this. Nett shares "must add up to the payment exactly", and
"rounding each share to the cent will not do that on its own". A statement's deductions "must sum
to the printed Nett exactly, to the cent". Neither is a tolerance -- they are equalities, and the
operator settles real money against the result.

Everything here is a pure function over `Decimal`. No floats, no database, no rounding that loses
a cent to nobody.
"""
