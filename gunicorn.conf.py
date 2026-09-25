"""Configuration Gunicorn : masque la signature du serveur.

Gunicorn pose son propre en-tête « Server » avant ceux de l'application, et
celui-ci l'emporte. On remplace donc la valeur à la source plutôt que dans une
réponse Flask.
"""

import gunicorn

gunicorn.SERVER = "ShyClone"
gunicorn.SERVER_SOFTWARE = "ShyClone"
