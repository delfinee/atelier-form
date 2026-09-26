"""Identify the one database conflict that has normal review feedback."""


def is_duplicate_review_error(error):
    cause = error.__cause__
    return (
        getattr(cause, "sqlstate", None) == "23505"
        and getattr(getattr(cause, "diag", None), "constraint_name", None)
        == "one_review_per_product_per_user"
    )
