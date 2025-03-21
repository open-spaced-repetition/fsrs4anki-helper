def fast_poisson_binomial_pmf(p):
    """
    Calculate the exact PMF of the Poisson Binomial distribution using
    dynamic programming.

    Parameters:
    -----------
    p : list or tuple
        List of success probabilities for each Bernoulli trial

    Returns:
    --------
    list of PMF values for k=0,1,...,len(p)
    """
    # Convert input to list if it's not already
    p = list(p)
    n = len(p)

    # Validate input
    for prob in p:
        if not 0 <= prob <= 1:
            raise ValueError("All probabilities must be between 0 and 1")

    # Handle trivial cases
    if n == 0:
        return [1.0]

    # Initialize the PMF - we'll use a dynamic programming approach
    # pmf[j] will represent P(X = j) after considering the first i trials
    pmf = [0.0] * (n + 1)
    pmf[0] = 1.0  # Base case: probability of 0 successes with 0 trials is 1

    # Process each probability one at a time
    for prob in p:
        # For each new Bernoulli trial, we update the entire PMF
        # We do this in reverse order to avoid overwriting values we still need
        for j in range(n, 0, -1):
            pmf[j] = pmf[j] * (1 - prob) + pmf[j - 1] * prob

        # Update the probability of zero successes
        pmf[0] = pmf[0] * (1 - prob)

    return pmf
