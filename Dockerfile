FROM php:8.2-apache

# Copy website files
COPY src/ /var/www/html/

RUN a2enmod rewrite deflate headers

# De receptendatabase is een paar megabyte json; gecomprimeerd verstuurd scheelt
# ongeveer 80 procent aan laadtijd.
COPY docker/smartlist.conf /etc/apache2/conf-available/smartlist.conf
RUN a2enconf smartlist

# Expose port 80
EXPOSE 80
