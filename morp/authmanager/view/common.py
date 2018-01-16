
from ..app import App
from ..exc import AuthManagerError


@App.json(model=AuthManagerError)
def exception_view(context, request):
    @request.after
    def adjust_status(response):
        response.status = 422
    return {
        'status': 'error',
        'error': {
            'type': context.__class__.__name__,
            'message': str(context)
        }
    }
