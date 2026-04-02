#
#   Vinly Collection Sorter - Discogs access module
#   MQM 2025-05-26
#
#   This is the module to log into Discogs and provide any common access logic. We are
#   keeping it seperate for the sake of making it better in the future.
#


#   Standard library imports
import logging
import time
import functools
import requests

#   Third party imports
import discogs_client

#   Local imports

#
#   Discogs access processing
#


def discogs_rate_limit_handler(func):
    """Decorator that handles Discogs rate limiting based on response codes."""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        max_retries = 3
        base_delay = 1.0

        for attempt in range(max_retries + 1):
            try:
                # Wait before request (except first attempt)
                if attempt > 0:
                    delay = base_delay * (2 ** (attempt - 1))  # Exponential backoff
                    logging.debug(f"{delay} second wait before Discogs access #{attempt}.")
                    time.sleep(delay)

                result = func(*args, **kwargs)

                # If function returns a response object, check it
                if hasattr(result, 'status_code'):
                    if result.status_code == 429:
                        if attempt < max_retries:
                            retry_after = result.headers.get('Retry-After', base_delay * 2)
                            logging.warning(f"Discogs limited, waiting {retry_after} seconds.")
                            time.sleep(int(retry_after))
                            continue
                        else:
                            logging.error("Max retries reached for rate limiting")
                            return result
                    elif result.status_code in [500, 502, 503, 504]:
                        if attempt < max_retries:
                            logging.warning(f"Discogs error {result.status_code}, retrying...")
                            continue

                return result

            except requests.exceptions.RequestException as e:
                if attempt < max_retries:
                    logging.warning(f"Request failed: {e}, retrying...")
                    continue
                else:
                    logging.error(f"Max retries reached: {e}")
                    raise

        return result

    return wrapper


@discogs_rate_limit_handler
def discogs_login():
    """Log into Discogs nicely."""
    login_object = discogs_client.Client('$DISCOGS_ID', user_token='$DISCOGS_TOKEN')
    login_user = login_object.identity()
    logging.debug(f"Logged into Discogs as {login_user}.")

    return(login_object, login_user)
