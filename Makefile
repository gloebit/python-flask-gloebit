#
#
#

all:

install: uninstall
	sudo ln -s $(PWD) /var/www/python-flask-gloebit
	sudo ln -s $$PWD/python-flask-gloebit.conf /etc/apache2/sites-enabled/python-flask-gloebit.conf

uninstall:
	sudo rm -f /var/www/python-flask-gloebit
	sudo rm -f /etc/apache2/sites-enabled/python-flask-gloebit.conf

clean:
	rm -f *~ */*~
