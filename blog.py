#!/usr/bin/env python
#
# Copyright 2014 Aditya Pn


import functools
import os.path
import re
import tornado.escape
import tornado.web
import tornado.wsgi
import unicodedata

from google.appengine.api import users
from google.appengine.ext import db


class Entry(db.Model):
    """A single blog entry."""
    author = db.UserProperty()
    title = db.StringProperty(required=True)
    slug = db.StringProperty(required=True)
    body_source = db.TextProperty(required=True)
    html = db.TextProperty(required=True)
    published = db.DateTimeProperty(auto_now_add=True)
    updated = db.DateTimeProperty(auto_now=True)


def administrator(method):
    """Decorate with this method to restrict to site admins."""
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        if not self.current_user:
            if self.request.method == "GET":
                self.redirect(self.get_login_url())
                return
            raise tornado.web.HTTPError(403)
        elif not self.current_user.administrator:
            if self.request.method == "GET":
                self.redirect("/")
                return
            raise tornado.web.HTTPError(403)
        else:
            return method(self, *args, **kwargs)
    return wrapper


class BaseHandler(tornado.web.RequestHandler):
    """Implements Google Accounts authentication methods."""
    def get_current_user(self):
        user = users.get_current_user()
        if user: user.administrator = users.is_current_user_admin()
        return user

    def get_login_url(self):
        return users.create_login_url(self.request.uri)

    def get_template_namespace(self):
        # Let the templates access the users module to generate login URLs
        ns = super(BaseHandler, self).get_template_namespace()
        ns['users'] = users
        return ns


class HomeHandler(BaseHandler):
    def get(self):
        entries = db.Query(Entry).order('-published').fetch(limit=5)
        if not entries:
            if not self.current_user or self.current_user.administrator:
                self.redirect("/compose")
                return
        self.render("home.html", entries=entries)


class EntryHandler(BaseHandler):
    def get(self, slug):
        entry = db.Query(Entry).filter("slug =", slug).get()
        if not entry: raise tornado.web.HTTPError(404)
        self.render("entry.html", entry=entry)


class ArchiveHandler(BaseHandler):
    def get(self):
        entries = db.Query(Entry).order('-published')
        self.render("archive.html", entries=entries)


class FeedHandler(BaseHandler):
    def get(self):
        entries = db.Query(Entry).order('-published').fetch(limit=10)
        self.set_header("Content-Type", "application/atom+xml")
        self.render("feed.xml", entries=entries)

class AboutHandler(BaseHandler):
    def get(self):
        self.render("about.html",me="you")

class MeHandler(BaseHandler):
    def get(self):
        self.render("me.html",me="yes")

class ComposeHandler(BaseHandler):
    @administrator
    def get(self):
        key = self.get_argument("key", None)
        entry = Entry.get(key) if key else None
        self.render("compose.html", entry=entry)

    @administrator
    def post(self):
        key = self.get_argument("key", None)
        if key:
            entry = Entry.get(key)
            entry.title = self.get_argument("title")
            entry.body_source = self.get_argument("body_source")
            entry.html = self.get_argument("body_source")
        else:
            title = self.get_argument("title")
            slug = unicodedata.normalize("NFKD", title).encode(
                "ascii", "ignore")
            slug = re.sub(r"[^\w]+", " ", slug)
            slug = "-".join(slug.lower().strip().split())
            if not slug: slug = "entry"
            while True:
                existing = db.Query(Entry).filter("slug =", slug).get()
                if not existing or str(existing.key()) == key:
                    break
                slug += "-2"
            entry = Entry(
                author=self.current_user,
                title=title,
                slug=slug,
                body_source=self.get_argument("body_source"),
                html=self.get_argument("body_source"),
            )
        entry.put()
        self.redirect("/entry/" + entry.slug)


class EntryModule(tornado.web.UIModule):
    def render(self, entry):
        url = self.request.protocol+"://"+ self.request.host+ self.request.uri
        return self.render_string("modules/entry.html", entry=entry,url=url)




settings = {
    "blog_title": u"Aditya Pn's Blog",
    "template_path": os.path.join(os.path.dirname(__file__), "templates"),
    "ui_modules": {"Entry": EntryModule},
    "xsrf_cookies": True,
}
application = tornado.wsgi.WSGIApplication([
    (r"/", ArchiveHandler),    
    (r"/about", AboutHandler),
    (r"/me", MeHandler),
    (r"/feed", FeedHandler),
    (r"/entry/([^/]+)", EntryHandler),
    (r"/compose", ComposeHandler),
], **settings)
