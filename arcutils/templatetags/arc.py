import json
import posixpath

from django import template
from django.conf import settings
from django.contrib.staticfiles.storage import staticfiles_storage
from django.core.exceptions import ImproperlyConfigured
from django.utils.safestring import mark_safe

try:
    import markdown as _markdown
except ImportError:
    _markdown = None

from arcutils.exc import ARCUtilsDeprecationWarning
from arcutils.settings import get_setting
from arcutils.staticfiles import load_manifest as load_staticfiles_manifest


register = template.Library()


@register.simple_tag
def cdn_url(path, scheme=None):
    """Generate a CDN URL like '//cdn.research.pdx.edu/some/path'.

    URLs generated by this function will not include an explicit scheme
    unless a ``scheme`` is passed. In most cases, not including the
    scheme is preferable because the browser will automatically use the
    scheme that was used to load the page.

    ``path`` can be a path or a key from the ``ARC['cdn']['paths']``
    setting.

    Example::

        {% load arc %}
        <script src="{% cdn_url 'jquery/2.1.1/jquery-2.1.1.min.js %}"></script>

    To inject a version from the ``ARC['versions']`` setting into the
    URL, include ``{key}`` somewhere in ``path``. E.g.::

        <script src="{% cdn_url 'jquery/{jquery}/jquery-{jquery}.min.js' %}</script>

    Another option is to define paths via the ``ARC['cdn']['paths']``
    setting. For example::

        # In the project's settings:
        ARC['cdn']['paths'] = {
            'jquery-js': 'jquery/{jquery}/jquery-{jquery}.min.js',
            ...
        }

        # Or, if using django-local-settings:
        ARC.cdn.paths.jquery-js = "jquery/{jquery}/jquery-{jquery}.min.js"

        # In a template:
        {% load arc %}
        <script src="{% cdn_url 'jquery-js' %}"></script>

    The latter form allows the CDN URL for a particular resource to be
    defined in a single place for easy reuse and updating.

    """
    host = get_setting('ARC.cdn.host', 'cdn.research.pdx.edu')
    path = get_setting('ARC.cdn.paths.%s' % path, path)
    versions = get_setting('ARC.versions', {})
    path = path.format(**versions)
    url = '//{host}/{path}'.format(host=host, path=path.lstrip('/'))
    if scheme is not None:
        url = '{scheme}:{url}'.format(scheme=scheme, url=url)
    return mark_safe(url)


@register.simple_tag
def google_analytics(tracking_id=None, cookie_domain=None, tracker_name=None, fields=None):
    """Generate a configured Google Analytics <script> tag.

    The args to this tag correspond to the args to GA's ``create``
    command.

    When ``DEBUG`` mode is enabled, an HTML comment placeholder will be
    returned instead of the GA <script> tag.

    If a ``tracking_id`` is passed when calling the tag, that ID will be
    used. Otherwise, if the ``GOOGLE.analytics.tracking_id`` is present
    and contains a value, that ID will be used.

    If a tracking ID isn't passed or found in the settings, then a
    placeholder HTML comment will be returned instead of the GA <script>
    tag.

    The remaining args are optional. They can be passed directly or
    added to the 'GOOGLE.analytics.*' settings namespace. The defaults
    are (expressed as JavaScript values):

        - cookie_domain: 'auto'
        - tracker_name: undefined
        - fields: undefined

    ``cookie_domain`` and ``tracker_name`` should be strings. ``fields``
    should be a dict with simple values that can be converted to JSON (I
    don't think we'll have much need for ``fields``; see the GA docs for
    what it can contain).

    """
    tracking_id = tracking_id or get_setting('GOOGLE.analytics.tracking_id', None)
    if tracking_id and not settings.DEBUG:
        cookie_domain = cookie_domain or get_setting('GOOGLE.analytics.cookie_domain', 'auto')
        tracker_name = tracker_name or get_setting('GOOGLE.analytics.tracker_name', None)
        fields = fields or get_setting('GOOGLE.analytics.fields', None)
        value = """
            <script>
                (function(i,s,o,g,r,a,m){i['GoogleAnalyticsObject']=r;i[r]=i[r]||function(){
                (i[r].q=i[r].q||[]).push(arguments)},i[r].l=1*new Date();a=s.createElement(o),
                m=s.getElementsByTagName(o)[0];a.async=1;a.src=g;m.parentNode.insertBefore(a,m)
                })(window,document,'script','//www.google-analytics.com/analytics.js','ga');

                ga(
                    'create',
                    '%(tracking_id)s',    // Tracking ID
                    '%(cookie_domain)s',  // Cookie domain
                    %(tracker_name)s,     // Tracker name
                    %(fields)s            // Fields
                );

                ga('send', 'pageview');
            </script>
        """ % {
            'tracking_id': tracking_id,
            'cookie_domain': cookie_domain,
            'tracker_name': "'%s'" % tracker_name if tracker_name else 'undefined',
            'fields': json.dumps(fields) if fields else 'undefined',
        }
    else:
        value = '<!-- Google Analytics code goes here -->'
    return mark_safe(value)


@register.filter
def jsonify(obj):
    return mark_safe(json.dumps(obj))


@register.filter
def markdown(content):
    if _markdown is None:
        raise ImproperlyConfigured('Markdown must be installed to use the markdown template filter')
    return mark_safe(_markdown.markdown(content))


@register.simple_tag
def require_block(app_name, *cdn_urls):
    """Output <script> tags for loading a RequireJS entry point.

    This chooses the appropriate scripts according to the ``DEBUG``
    setting. In debug mode, this outputs the following tags::

        <script src="/static/requireConfig.js"></script>
        <script src="/static/vendor/requirejs/require.js"></script>
        <script src="/static/{app_name}/main.js"></script>

    In production, this outputs the following tags::

        <script src="/static/vendor/almond/almond.js"></script>
        ... CDN <script>s ...
        <script src="/static/{app_name}/main-built.js"></script>

    .. note:: These examples assume STATIC_URL is set to '/static/'.

    requireConfig.js must be in the project's top level static directory
    and contain RequireJS config like this::

        var require = {
            baseUrl: '/static',  // Same as STATIC_URL, minus trailing slash
            paths: {
                almond: 'vendor/almond/almond',
                ng: 'vendor/angular/angular',
                ...,
                quickticket: '.'  // Replace quickticket with project name
            }
            shim: {
                ng: {
                    exports: 'angular'
                },
                ngResource: {
                    deps: ['ng']
                },
                ...
            }
        }

    """
    debug = settings.DEBUG
    file_name = 'main.js' if debug else 'main-built.js'
    entry_point = posixpath.join(app_name, file_name)
    scripts = []
    if debug:
        scripts.append(staticfiles_storage.url('requireConfig.js'))
        scripts.append(staticfiles_storage.url('vendor/requirejs/require.js'))
    else:
        scripts.append(staticfiles_storage.url('vendor/almond/almond.js'))
        for src in cdn_urls:
            scripts.append(cdn_url(src))
    scripts.append(staticfiles_storage.url(entry_point))
    scripts = ['<script src="{src}"></script>'.format(src=s) for s in scripts]
    scripts = '\n    '.join(scripts)
    return mark_safe(scripts)


@register.simple_tag
def staticfiles_manifest(*paths, as_json=True):
    """Get manifest for static files.

    .. note:: This is experimental; use with caution.

    Provides a way to pass the static files manifest to JavaScript
    when using Django's ``ManifestStaticFilesStorage``. If ``paths`` are
    passed, the manifest will be filtered to include only matching
    paths; otherwise, all paths will be included (note: the manifest can
    be quite large in some cases, so filtering it may be a good idea).

    See :func:`arcutils.staticfiles.load_manifest` for more details.

    Example usage::

        <script>
            var STATIC_URL = {% static '' %},
                STATICFILES_MANIFEST = {% staticfiles_manifest 'app/*' %};

            // Analogous to {% static 'path/to/some/file' %}
            function staticUrl (path) {
                if (STATICFILES_MANIFEST) {
                    STATICFILES_MANIFEST[path]
                }
                // NOTE: This assumes STATIC_URL ends with a slash and
                //       the path does *not* start with a slash.
                return [STATIC_URL, path].join('');
            }

            // Then, in front end app code:
            var url = staticUrl('path/to/some/file');
        </script>

    """
    manifest = load_staticfiles_manifest(*paths)
    if as_json:
        manifest = mark_safe(json.dumps(manifest))
    return manifest


# Legacy template tags. DO NOT use in new code. These are here to ease
# the migration from ARCUtils v1 to v2.


@register.simple_tag(takes_context=True)
def add_get(context, **params):
    ARCUtilsDeprecationWarning.warn('The add_get template tag is deprecated')
    request = context['request']
    request_params = request.GET.copy()
    for name, value in params.items():
        request_params[name] = value
    return '?{query_string}'.format(query_string=request_params.urlencode())


@register.filter
def model_name(model):
    ARCUtilsDeprecationWarning.warn('The model_name template filter is deprecated')
    return model._meta.verbose_name.title()
