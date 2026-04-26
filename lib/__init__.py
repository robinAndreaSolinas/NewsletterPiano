import logging
from .utils import *

package_logger = logging.getLogger(__name__)
package_logger.setLevel(logging.DEBUG)

__author__ = 'Andrea Solinas'
__version__ = '0.1.0'
__all__ = [
    "PianoESP",
    "APIException",
    "APIClientException",
    "AbstractAPIClient",
    "Singleton",
    "camel_to_snake"
]