class AuthManagerError(Exception):
    pass


class InvalidPasswordError(AuthManagerError):
    pass


class UserExistsError(AuthManagerError):
    pass


class GroupExistsError(AuthManagerError):
    pass


class GroupDoesNotExistsError(AuthManagerError):
    pass


class UserDoesNotExistsError(AuthManagerError):
    pass


class MembershipError(AuthManagerError):

    def __init__(self, user, group, *args, **kwargs):
        msg = "User %s not in group %s" % (user, group)
        super(MembershipError, self).__init__(msg, *args, **kwargs)
