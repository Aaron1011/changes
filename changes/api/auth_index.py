from __future__ import absolute_import, division, unicode_literals

from flask import session

from changes.api.base import APIView


class AuthIndexAPIView(APIView):
    def get(self):
        """
        Return information on the currently authenticated user.
        """
        if session.get('email'):
            context = {
                'authenticated': True,
                'user': {
                    'email': session['email'],
                },
            }
        else:
            context = {
                'authenticated': False,
            }

        return self.respond(context)
