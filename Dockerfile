FROM php:8.2-apache

# Copy website files
COPY src/ /var/www/html/

# Enable mod_rewrite (optional for clean URLs)
RUN a2enmod rewrite

# Expose port 80
EXPOSE 80
